"""
ZOE GBA 한글 패치 v7 — 2바이트 폰트 확장 (845음절 전부 지원)

핵심 변경 (v5/v6 대비):
- 단일바이트 0x80~0xFE(127슬롯) → 2바이트 코드 0x200+i (사실상 무제한)
- 파서 수정 불필요: ROM 파서가 리드바이트 0x01~0x0F를 2바이트 문자로 native 처리
- 너비 테이블 패치 불필요: 코드>0x1FE & cache≥0 → 자동 12px
- 글리프: Galmuri11.bdf (11px 비트맵, 픽셀퍼펙트)

레이아웃:
 - 훅      ROM 0x038AC (8 bytes 교체)
 - 트램폴린 ROM 0x78C540 (60 bytes)
 - 글리프   ROM 0x78C580 (N_TABLE*32 bytes)
"""
import struct, os, sys, io, json, re
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

ROM_PATH  = r"D:\Works\zoe\Zone of the Enders - The Fist of Mars (USA).gba"
OUT_ROM   = r"D:\Works\zoe\ZOE_Korean_v7.gba"
BDF_PATH  = r"D:\Works\zoe\galmuri_extracted\Galmuri11.bdf"
CACHE_PATH= r"D:\Works\zoe\translation_cache.json"
TEXT_PATH = r"D:\Works\zoe\extracted_text.txt"
SYLL_OUT  = r"D:\Works\zoe\syllable_index_v7.json"

# ---- 주소 상수 ----
GBA_ROM_BASE       = 0x08000000
IWRAM_BASE         = 0x03003320
HOOK_ROM_OFF       = 0x038AC
ENGLISH_RESUME_GBA = 0x080038B5      # 0x38B4 + Thumb bit
TRAMPOLINE_ROM_OFF = 0x78C540
GLYPH_ROM_OFF      = 0x78C580
TRAMPOLINE_GBA     = GBA_ROM_BASE + TRAMPOLINE_ROM_OFF
GLYPH_GBA          = GBA_ROM_BASE + GLYPH_ROM_OFF

KOREAN_CODE_BASE   = 0x200            # 음절 i → 코드 0x200+i
N_TABLE            = 0x400            # 글리프 테이블 크기(1024). 코드 0x200~0x5FF 안전 커버

def u32le(v): return [(v>>0)&0xFF,(v>>8)&0xFF,(v>>16)&0xFF,(v>>24)&0xFF]

# ============================================================
# 1. 필요 음절 수집 + 인덱스 부여 (빈도순)
# ============================================================
print("=== 음절 인덱스 생성 ===")
cache = json.load(open(CACHE_PATH, encoding='utf-8'))
freq = {}
for v in cache.values():
    for ch in v:
        if 0xAC00 <= ord(ch) <= 0xD7A3:
            freq[ch] = freq.get(ch, 0) + 1
syllables = sorted(freq, key=lambda c: (-freq[c], c))   # 빈도 내림차순
assert len(syllables) <= N_TABLE, f"음절 {len(syllables)} > 테이블 {N_TABLE}"
SYLL_TO_IDX = {ch: i for i, ch in enumerate(syllables)}
json.dump(SYLL_TO_IDX, open(SYLL_OUT,'w',encoding='utf-8'), ensure_ascii=False)
print(f"  고유 음절 {len(syllables)}개 → 코드 0x{KOREAN_CODE_BASE:X}~0x{KOREAN_CODE_BASE+len(syllables)-1:X}")
print(f"  최빈 음절: {''.join(syllables[:15])}")

# ============================================================
# 2. Galmuri11.bdf 파싱 → 16x16 1bpp 글리프
# ============================================================
print("\n=== 글리프 생성 (Galmuri11) ===")
def parse_bdf(path):
    glyphs = {}
    lines = open(path, encoding='utf-8').readlines()
    i = 0
    while i < len(lines):
        if lines[i].startswith('STARTCHAR'):
            enc=None; bbx=(0,0,0,0); rows=[]; inb=False; i+=1
            while i < len(lines):
                l = lines[i].strip()
                if l.startswith('ENCODING'): enc=int(l.split()[1])
                elif l.startswith('BBX'):
                    p=l.split(); bbx=(int(p[1]),int(p[2]),int(p[3]),int(p[4]))
                elif l=='BITMAP': inb=True
                elif l=='ENDCHAR': break
                elif inb: rows.append(l)
                i+=1
            if enc is not None and rows:
                bw=bbx[0]; hexbits=(((bw+7)//8 +1)&~1)*8
                grid=[]
                for hs in rows:
                    val=int(hs,16)
                    grid.append([1 if (val>>(hexbits-1-b))&1 else 0 for b in range(bw)])
                glyphs[enc]={'rows':grid,'bbx':bbx}
        i+=1
    return glyphs

bdf = parse_bdf(BDF_PATH)
X_OFFSET, Y_OFFSET = 1, 2   # 11px 글리프를 16x16 캔버스 좌상단 근처에 배치(12px 폭 내 수렴)

def glyph_1bpp(g):
    canvas=[[0]*16 for _ in range(16)]
    for r,row in enumerate(g['rows']):
        y=Y_OFFSET+r
        if y>=16: break
        for c,px in enumerate(row):
            x=X_OFFSET+c
            if x>=16: break
            canvas[y][x]=px
    data=bytearray(32)
    for r in range(16):
        for c in range(16):
            if canvas[r][c]:
                if c<8: data[r*2]   |= 1<<(7-c)
                else:   data[r*2+1] |= 1<<(15-c)
    return bytes(data)

glyph_data = bytearray()
missing=[]
for i in range(N_TABLE):
    if i < len(syllables):
        cp = ord(syllables[i])
        if cp in bdf: glyph_data += glyph_1bpp(bdf[cp])
        else: glyph_data += bytes(32); missing.append(syllables[i])
    else:
        glyph_data += bytes(32)   # 미사용 슬롯 = 빈 글리프
assert len(glyph_data) == N_TABLE*32
print(f"  글리프 데이터: {len(glyph_data)} bytes ({N_TABLE} 슬롯)")
if missing: print(f"  경고: BDF 누락 {len(missing)}개: {missing[:10]}")
# 미리보기
def preview(d):
    for r in range(16):
        print("  "+''.join('#' if ((d[r*2] if c<8 else d[r*2+1])>>((7-c) if c<8 else (15-c)))&1 else '.' for c in range(16)))
print(f"  '{syllables[0]}' 미리보기:")
preview(glyph_data[:32])

# ============================================================
# 3. 트램폴린 (Thumb-1, 손어셈블) — 레이아웃은 PLAN_v7.md 참조
# ============================================================
print("\n=== 트램폴린 빌드 ===")
# 분기 오프셋: english 경로 = +24
# BLO @+04: PC=+08, (0x24-0x08)/2=0x0E
# BHS @+08: PC=+0C, (0x24-0x0C)/2=0x0C
# LDR r2 @+14: PC=(+18)&~2=+18, pool_iwram@+30 → imm=(0x30-0x18)=0x18 → /4=6
# LDR r0 @+1E: PC=(+22)&~2=+20, pool_glyph@+34 → imm=0x14 → /4=5
# LDR r0 @+2C: PC=(+30)&~2=+30, pool_eng@+38   → imm=0x08 → /4=2
tramp = bytearray([
    0x0A,0x0A,            # +00 LSRS r2,r1,#8
    0x02,0x2A,            # +02 CMP  r2,#2
    0x0E,0xD3,            # +04 BLO  english(+24)
    0x06,0x2A,            # +06 CMP  r2,#6
    0x0C,0xD2,            # +08 BHS  english(+24)
    0x80,0x39,            # +0A SUBS r1,#0x80
    0x80,0x39,            # +0C SUBS r1,#0x80
    0x80,0x39,            # +0E SUBS r1,#0x80
    0x80,0x39,            # +10 SUBS r1,#0x80   ; r1 = code-0x200 = idx
    0x43,0x01,            # +12 LSLS r3,r0,#5   ; slot*32
    0x06,0x4A,            # +14 LDR  r2,[pc,#0x18] → pool_iwram
    0xD3,0x18,            # +16 ADDS r3,r3,r2
    0x00,0x22,            # +18 MOVS r2,#0
    0xDA,0x77,            # +1A STRB r2,[r3,#31]
    0x49,0x01,            # +1C LSLS r1,r1,#5   ; idx*32
    0x05,0x48,            # +1E LDR  r0,[pc,#0x14] → pool_glyph
    0x40,0x18,            # +20 ADDS r0,r0,r1
    0x70,0x47,            # +22 BX   lr
    # english (+24): 원본 0x38AC 4명령 재현 후 0x38B4 복귀
    0x30,0xB5,            # +24 PUSH {r4,r5,lr}
    0x04,0x1C,            # +26 ADDS r4,r0,#0
    0x24,0x06,            # +28 LSLS r4,r4,#0x18
    0x09,0x04,            # +2A LSLS r1,r1,#0x10
    0x02,0x48,            # +2C LDR  r0,[pc,#8] → pool_eng
    0x00,0x47,            # +2E BX   r0
    # pools (4정렬: base+0x30)
    *u32le(IWRAM_BASE),         # +30
    *u32le(GLYPH_GBA),          # +34
    *u32le(ENGLISH_RESUME_GBA), # +38
])
assert len(tramp) == 0x3C, f"트램폴린 크기 {len(tramp):#x} (기대 0x3C)"
print(f"  트램폴린: {len(tramp)} bytes")

# ---- capstone 자가검증 ----
try:
    import capstone
    md=capstone.Cs(capstone.CS_ARCH_ARM, capstone.CS_MODE_THUMB)
    print("  [자가검증] 트램폴린 역어셈블:")
    for ins in md.disasm(bytes(tramp[:0x30]), TRAMPOLINE_GBA):
        print(f"    {ins.address:08X}: {ins.mnemonic:6} {ins.op_str}")
except Exception as e:
    print("  capstone 검증 건너뜀:", e)

# ============================================================
# 4. 훅 패치
# ============================================================
TRAMP_THUMB = TRAMPOLINE_GBA | 1
hook = bytearray([0x00,0x48, 0x00,0x47, *u32le(TRAMP_THUMB)])  # LDR r0,[pc,#0]; BX r0; .word
assert len(hook)==8

# ============================================================
# 5. ROM 로드 & 패치
# ============================================================
print("\n=== ROM 패치 ===")
rom = bytearray(open(ROM_PATH,'rb').read())
orig = bytes(rom[HOOK_ROM_OFF:HOOK_ROM_OFF+4])
print(f"  훅 원본 0x{HOOK_ROM_OFF:05X}: {orig.hex()} (기대 30b5041c)")
assert orig == bytes([0x30,0xB5,0x04,0x1C]), "원본 훅 불일치 — 원본 ROM인지 확인"
assert all(b==0xFF for b in rom[TRAMPOLINE_ROM_OFF:TRAMPOLINE_ROM_OFF+0x40]), "트램폴린 영역 비어있지 않음"
assert all(b==0xFF for b in rom[GLYPH_ROM_OFF:GLYPH_ROM_OFF+len(glyph_data)]), "글리프 영역 비어있지 않음"

rom[HOOK_ROM_OFF:HOOK_ROM_OFF+8]                       = hook
rom[TRAMPOLINE_ROM_OFF:TRAMPOLINE_ROM_OFF+len(tramp)]  = tramp
rom[GLYPH_ROM_OFF:GLYPH_ROM_OFF+len(glyph_data)]       = glyph_data

# ============================================================
# 6. 텍스트 인코딩 & 삽입
# ============================================================
print("\n=== 텍스트 삽입 ===")
def encode(text):
    out=bytearray()
    for ch in text:
        cp=ord(ch)
        if 0xAC00<=cp<=0xD7A3:
            if ch in SYLL_TO_IDX:
                code=KOREAN_CODE_BASE+SYLL_TO_IDX[ch]
                out.append((code>>8)&0xFF); out.append(code&0xFF)
            # 미지원 음절은 건너뜀(이론상 없음)
        elif ch==' ': out.append(0x20)
        elif ch=='\n': out += b'\x12\x11'
        elif ch.isascii() and 0x21<=cp<=0x7E:
            rb=cp-6
            if rb>=0x1A: out.append(rb)
    return bytes(out)

VALID = set(range(0x1A,0x79)) | {0x20} | set(range(0x00,0x10))
def valid_block(off,length):
    if off+length+1>=len(rom) or length<3: return False
    v=0
    for i in range(min(length,20)):
        b=rom[off+i]
        if b in VALID: v+=1
        elif b==0x00: break
        else: return False
    return v>=2

content=open(TEXT_PATH,encoding='utf-8-sig').read()
blocks=[]
for b in content.split('\n[OFFSET:'):
    b=b.lstrip('[OFFSET:').strip()
    if not b: continue
    ls=b.split('\n')
    try: off=int(ls[0].rstrip(']'),16)
    except: continue
    txt='\n'.join(ls[1:]).strip()
    if txt:
        cl=re.sub(r'[\x00-\x1F\x80-\xFF]','',txt)
        cl=re.sub(r"[^A-Za-z0-9 \.,!?'-]",' ',cl)
        cl=re.sub(r'\s+',' ',cl).strip()
        if cl: blocks.append((off,cl))
blocks.sort()

replaced=truncated=skipped=0
for off,eng in blocks:
    kor=cache.get(eng,'')
    if not kor: skipped+=1; continue
    if not valid_block(off,len(eng)): skipped+=1; continue
    kb=encode(kor)
    if not kb: skipped+=1; continue
    if len(kb)>len(eng):
        kb=kb[:len(eng)]; truncated+=1
    rom[off:off+len(kb)]=kb
    rom[off+len(kb)]=0x00
    replaced+=1
print(f"  삽입 {replaced}개 (truncate {truncated}, skip {skipped})")

open(OUT_ROM,'wb').write(rom)
print(f"\n=== 완료 ===")
print(f"  출력: {OUT_ROM}")
print(f"  훅 0x{HOOK_ROM_OFF:05X}: {bytes(hook).hex()}")
print(f"  트램폴린 0x{TRAMPOLINE_ROM_OFF:06X}, 글리프 0x{GLYPH_ROM_OFF:06X} ({N_TABLE}슬롯)")
print(f"  mGBA로 ZOE_Korean_v7.gba 실행 후 인트로/대사 확인")
