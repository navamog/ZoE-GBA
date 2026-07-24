"""
ZOE GBA 한글 패치 v5 (처음부터 새로 작성)

핵심 수정사항:
1. 보조 너비 테이블(0x553476)도 패치
2. 트램폴린: 한글 경로에서 IWRAM[slot*32+31]=0 설정 (너비 테이블 선택 보장)
3. 음절 수: 127개 (기존 syllable_index.json 유지)
4. 번역 캐시: translation_cache.json 사용

구조:
 - 트램폴린: ROM 0x78C540 (52 bytes)
 - 글리프: ROM 0x78C580 (127*32 = 4064 bytes)
 - 훅: ROM 0x038AC (8 bytes 교체)
"""
import struct, os, sys, io, json, re, ctypes, ctypes.wintypes
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

ROM_PATH  = r"D:\Works\zoe\Zone of the Enders - The Fist of Mars (USA).gba"
OUT_ROM   = r"D:\Works\zoe\ZOE_Korean_v6.gba"

# ============================================================
# 주소 상수
# ============================================================
GBA_ROM_BASE       = 0x08000000
IWRAM_BASE         = 0x03003320   # 038AC가 사용하는 IWRAM 글리프 슬롯 베이스
HOOK_ROM_OFF       = 0x038AC      # 훅 위치 (8 bytes)
ENGLISH_RESUME_GBA = 0x080038B5   # 038B4 + 1 (Thumb bit)
TRAMPOLINE_ROM_OFF = 0x78C540     # 트램폴린 위치
GLYPH_ROM_OFF      = 0x78C580     # 글리프 데이터 위치 (트램폴린 뒤)
TRAMPOLINE_GBA     = GBA_ROM_BASE + TRAMPOLINE_ROM_OFF
GLYPH_GBA          = GBA_ROM_BASE + GLYPH_ROM_OFF
WIDTH_TABLE1_OFF   = 0x553676     # 기본 너비 테이블 (IWRAM 슬롯 캐시 유효 시)
WIDTH_TABLE2_OFF   = 0x553476     # 보조 너비 테이블 (캐시 미스 시)
MAX_SYLLABLES      = 127
KOREAN_WIDTH       = 12           # 한글 타일 너비(px)

def u32le(v):
    return [(v>>0)&0xFF, (v>>8)&0xFF, (v>>16)&0xFF, (v>>24)&0xFF]

# ============================================================
# 1. GDI로 한글 글리프 생성 (16x16 1bpp, 32 bytes/글리프)
# ============================================================
print("=== 글리프 생성 ===")

gdi32  = ctypes.windll.gdi32
user32 = ctypes.windll.user32

class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [("biSize",ctypes.c_uint32),("biWidth",ctypes.c_int32),
                ("biHeight",ctypes.c_int32),("biPlanes",ctypes.c_uint16),
                ("biBitCount",ctypes.c_uint16),("biCompression",ctypes.c_uint32),
                ("biSizeImage",ctypes.c_uint32),("biXPelsPerMeter",ctypes.c_int32),
                ("biYPelsPerMeter",ctypes.c_int32),("biClrUsed",ctypes.c_uint32),
                ("biClrImportant",ctypes.c_uint32)]

def render_glyph(char, W=16, H=16):
    """문자 하나를 16x16 흑백으로 렌더링, 픽셀 그리드 반환"""
    hdc = user32.GetDC(None)
    mem_dc = gdi32.CreateCompatibleDC(hdc)
    bih = BITMAPINFOHEADER()
    bih.biSize = ctypes.sizeof(BITMAPINFOHEADER)
    bih.biWidth = W; bih.biHeight = -H
    bih.biPlanes = 1; bih.biBitCount = 32; bih.biCompression = 0
    class BITMAPINFO(ctypes.Structure):
        _fields_ = [("bmiHeader", BITMAPINFOHEADER), ("bmiColors", ctypes.c_uint32*3)]
    bmi = BITMAPINFO(); bmi.bmiHeader = bih
    pbits = ctypes.c_void_p()
    hbmp = gdi32.CreateDIBSection(mem_dc, ctypes.byref(bmi), 0, ctypes.byref(pbits), None, 0)
    gdi32.SelectObject(mem_dc, hbmp)
    hbr = gdi32.CreateSolidBrush(0x00FFFFFF)
    rect = ctypes.wintypes.RECT(0, 0, W, H)
    user32.FillRect(mem_dc, ctypes.byref(rect), hbr)
    gdi32.DeleteObject(hbr)
    # Gulim 폰트 사용 (한글 지원)
    hfont = gdi32.CreateFontW(13, 0, 0, 0, 400, 0, 0, 0, 129, 0, 0, 0, 0, "Gulim")
    gdi32.SelectObject(mem_dc, hfont)
    gdi32.SetTextColor(mem_dc, 0x00000000)
    gdi32.SetBkMode(mem_dc, 1)
    buf = ctypes.create_unicode_buffer(char)
    gdi32.TextOutW(mem_dc, 1, 1, buf, 1)  # (1,1) 약간 오프셋으로 클리핑 방지
    pixels = (ctypes.c_uint32 * (W * H))()
    ctypes.memmove(pixels, pbits, W * H * 4)
    grid = []
    for r in range(H):
        row = [1 if (pixels[r*W+c] & 0xFFFFFF) == 0 else 0 for c in range(W)]
        grid.append(row)
    gdi32.DeleteObject(hfont)
    gdi32.DeleteObject(hbmp)
    gdi32.DeleteDC(mem_dc)
    user32.ReleaseDC(None, hdc)
    return grid

def grid_to_1bpp(grid, H=16, W=16):
    """
    16x16 픽셀 그리드 → 32바이트 1bpp
    각 행: [byte_hi, byte_lo]
    byte_hi: col 0-7 (MSB=col0)
    byte_lo: col 8-15 (MSB=col8)
    바이트 30-31은 0x00 (게임 렌더러가 마지막 행을 메타데이터로 사용)
    """
    data = bytearray(32)
    for r in range(min(H-1, 15)):  # row 15 제외 (마지막 2바이트 = 0x00)
        for c in range(W):
            if grid[r][c]:
                if c < 8:
                    data[r*2+0] |= (1 << (7-c))
                else:
                    data[r*2+1] |= (1 << (15-c))
    return bytes(data)

# 음절 인덱스 로드
with open(r"D:\Works\zoe\syllable_index.json", encoding="utf-8") as f:
    syll_dict = json.load(f)
syllables = [ch for ch, _ in sorted(syll_dict.items(), key=lambda x: x[1])[:MAX_SYLLABLES]]
print(f"음절 {len(syllables)}개 로드: {syllables[:5]}...")

glyph_data = bytearray()
for i, syl in enumerate(syllables):
    grid = render_glyph(syl)
    glyph_bytes = grid_to_1bpp(grid)
    glyph_data += glyph_bytes

assert len(glyph_data) == MAX_SYLLABLES * 32
print(f"글리프 데이터: {len(glyph_data)} bytes")

# 글리프 미리보기 (첫 번째 음절 '이')
grid0 = render_glyph(syllables[0])
print(f"'{syllables[0]}' 글리프 미리보기:")
for r in range(16):
    print("  " + "".join('#' if grid0[r][c] else '.' for c in range(16)))

# ============================================================
# 2. 트램폴린 코드 생성 (52 bytes)
# ============================================================
print("\n=== 트램폴린 빌드 ===")

# 트램폴린 레이아웃 (at TRAMPOLINE_GBA, 총 52 bytes = 0x34):
#
# 진입: r0=slot_idx, r1=tile_id
# (원본 038AC와 동일한 인터페이스)
#
# 한글 경로 (tile 0x80-0xFE):
#  +00: ADDS r2, r1, #0   ; r2 = tile_id
#  +02: SUBS r2, #0x80    ; r2 = tile_id - 0x80
#  +04: CMP  r2, #0x7E    ; (0x7E = 127-1)
#  +06: BHI  → +20        ; if > 0x7E (= tile > 0xFE), 영어 경로
#  +08: PUSH {lr}          ; 스택 보호 (r4-r5 불필요)
#  +0A: LSL  r3, r0, #5   ; r3 = slot * 32
#  +0C: LDR  r0,[PC,#12]  → pool_iwram@+1C = IWRAM_BASE
#  +0E: ADD  r3, r3, r0   ; r3 = IWRAM_BASE + slot*32
#  +10: MOV  r0, #0
#  +12: STRB r0, [r3, #31] ; IWRAM[slot*32+31] = 0 (너비 테이블 선택 보장)
#  +14: LSL  r2, r2, #5   ; r2 = (tile-0x80)*32
#  +16: LDR  r0,[PC,#8]   → pool_glyph@+20 = GLYPH_GBA
#  +18: ADD  r0, r2, r0   ; r0 = GLYPH_GBA + offset
#  +1A: POP  {pc}         ; return r0 = ROM glyph pointer
#  +1C: [pool_iwram = IWRAM_BASE]
#  +20: [pool_glyph = GLYPH_GBA]
#  +24: (영어 경로)
#  +24: PUSH {r4,r5,lr}   ; 원본 038AC +00
#  +26: MOV  r4, r0       ; 원본 038AC +02
#  +28: LSL  r4, r4, #24  ; 원본 038AC +04
#  +2A: LSL  r1, r1, #16  ; 원본 038AC +06
#  +2C: LDR  r0,[PC,#4]   → pool_eng@+34 = ENGLISH_RESUME_GBA
#  +2E: BX   r0           → 038B4
#  +30: [padding 00 00]
#  +32: [padding 00 00]
#  +34: [pool_eng = ENGLISH_RESUME_GBA]
#  총 0x38 = 56 bytes
#
# BHI offset 계산:
#  BHI at +06: PC = +06+4 = +0A, target = +24 (영어 경로)
#  imm8 = (+24 - +0A) / 2 = 0x1A / 2 = 0x0D

bhi_offset = (0x24 - 0x0A) // 2   # = 13 = 0x0D
assert bhi_offset == 13

# LDR r0,[PC,#12] at +0C: PC = +0C+4 = +10, aligned = +10, pool@+10+12 = +1C ✓
# LDR r0,[PC,#8]  at +16: PC = +16+4 = +1A, aligned = +18, pool@+18+8 = +20 ✓
# LDR r0,[PC,#4]  at +2C: PC = +2C+4 = +30, aligned = +30, pool@+30+4 = +34 ✓

# BHI 재계산: 새 레이아웃에서 영어 경로는 +14
# BHI at +06: PC = +06+4 = +0A, target = +14
# offset = (+14 - +0A) / 2 = 10/2 = 5
bhi_offset = (0x14 - 0x0A) // 2
assert bhi_offset == 5

# LDR r0,[PC,#4] at +0A: PC=+0E, aligned=+0C, pool=+0C+4=+10 ✓  (GLYPH_GBA)
# LDR r0,[PC,#4] at +1C: PC=+20, aligned=+20, pool=+20+4=+24 ✓  (ENGLISH_RESUME)

trampoline = bytearray([
    # +00: 한글 타일 체크
    0x0A, 0x1C,              # MOV r2, r1
    0x80, 0x3A,              # SUB r2, #0x80
    0x7E, 0x2A,              # CMP r2, #0x7E
    bhi_offset, 0xD8,        # BHI → +14 (English path)
    # +08: 한글 경로 (단순: ROM 글리프 포인터 직접 반환)
    0x52, 0x01,              # LSL r2, r2, #5    (r2 = index*32)
    0x01, 0x48,              # LDR r0, [PC, #4]  → pool@+10 = GLYPH_GBA
    0x10, 0x18,              # ADD r0, r2, r0    (r0 = GLYPH_GBA + index*32)
    0x70, 0x47,              # BX  lr            (return, LR = original caller)
    # +10: pool GLYPH_GBA
    *u32le(GLYPH_GBA),
    # +14: 영어 경로 (원본 038AC 4명령어 재현 후 038B4로 점프)
    0x30, 0xB5,              # PUSH {r4,r5,lr}   (원본 038AC+00)
    0x04, 0x1C,              # MOV  r4, r0       (원본 038AC+02)
    0x24, 0x06,              # LSL  r4, r4, #24  (원본 038AC+04)
    0x09, 0x04,              # LSL  r1, r1, #16  (원본 038AC+06)
    0x01, 0x48,              # LDR  r0, [PC, #4] → pool@+24 = ENGLISH_RESUME
    0x00, 0x47,              # BX   r0            → 038B4
    0x00, 0x00,              # padding
    0x00, 0x00,              # padding
    # +24: pool ENGLISH_RESUME_GBA
    *u32le(ENGLISH_RESUME_GBA),
])
assert len(trampoline) == 0x28, f"트램폴린 크기 오류: {len(trampoline)} (기대: 0x28=40)"
print(f"트램폴린: {len(trampoline)} bytes (BHI offset={bhi_offset})")

# 검증: 풀 주소
print(f"  pool_iwram: 트램폴린+0x1C = ROM 0x{TRAMPOLINE_ROM_OFF+0x1C:06X} = {hex(IWRAM_BASE)}")
print(f"  pool_glyph: 트램폴린+0x20 = ROM 0x{TRAMPOLINE_ROM_OFF+0x20:06X} = {hex(GLYPH_GBA)}")
print(f"  pool_eng:   트램폴린+0x34 = ROM 0x{TRAMPOLINE_ROM_OFF+0x34:06X} = {hex(ENGLISH_RESUME_GBA)}")

# ============================================================
# 3. 훅 패치 (8 bytes at 0x038AC)
# ============================================================
TRAMPOLINE_THUMB = TRAMPOLINE_GBA | 1
hook_patch = bytearray([
    0x00, 0x48,              # LDR r0, [PC, #0]  → pool at 038B0
    0x00, 0x47,              # BX  r0            → TRAMPOLINE_THUMB
    *u32le(TRAMPOLINE_THUMB),
])
assert len(hook_patch) == 8

# ============================================================
# 4. ROM 로드 및 패치 적용
# ============================================================
print("\n=== ROM 패치 ===")
with open(ROM_PATH, 'rb') as f:
    rom = bytearray(f.read())

# 검증
orig_hook = bytes(rom[HOOK_ROM_OFF:HOOK_ROM_OFF+4])
print(f"훅 원본 (038AC): {orig_hook.hex()} (기대: 30 b5 04 1c)")
if orig_hook != bytes([0x30, 0xB5, 0x04, 0x1C]):
    print("  경고: 원본 훅이 예상과 다릅니다! 이미 패치된 ROM을 사용하고 있을 수 있습니다.")

area_tramp = bytes(rom[TRAMPOLINE_ROM_OFF:TRAMPOLINE_ROM_OFF+4])
print(f"트램폴린 영역 첫 4바이트: {area_tramp.hex()} (기대: ff ff ff ff)")

area_glyph = bytes(rom[GLYPH_ROM_OFF:GLYPH_ROM_OFF+4])
print(f"글리프 영역 첫 4바이트: {area_glyph.hex()} (기대: ff ff ff ff)")

# 패치 적용
rom[HOOK_ROM_OFF         : HOOK_ROM_OFF+8]                          = hook_patch
rom[TRAMPOLINE_ROM_OFF   : TRAMPOLINE_ROM_OFF+len(trampoline)]      = trampoline
rom[GLYPH_ROM_OFF        : GLYPH_ROM_OFF+len(glyph_data)]          = glyph_data

# 너비 테이블 패치 (기본 + 보조 둘 다)
for tile in range(0x80, 0xFF):
    rom[WIDTH_TABLE1_OFF + tile] = KOREAN_WIDTH
    rom[WIDTH_TABLE2_OFF + tile] = KOREAN_WIDTH
print(f"너비 테이블 패치: tile 0x80~0xFE → {KOREAN_WIDTH}px (테이블 2개 모두)")

# ============================================================
# 5. 한글 텍스트 삽입
# ============================================================
print("\n=== 텍스트 삽입 ===")

SYLL_TO_IDX = {k: v for k, v in syll_dict.items() if v < MAX_SYLLABLES}

cache = {}
cache_path = r"D:\Works\zoe\translation_cache.json"
if os.path.exists(cache_path):
    with open(cache_path, encoding='utf-8') as f:
        cache = json.load(f)
print(f"번역 캐시: {len(cache)}개")

with open(r"D:\Works\zoe\extracted_text.txt", encoding='utf-8-sig') as f:
    content = f.read()

def parse_text_blocks(content):
    blocks = []
    for b in content.split('\n[OFFSET:'):
        b = b.lstrip('[OFFSET:').strip()
        if not b: continue
        lines = b.split('\n')
        try:
            offset = int(lines[0].rstrip(']'), 16)
        except:
            continue
        text = '\n'.join(lines[1:]).strip()
        if text:
            cleaned = re.sub(r'[\x00-\x1F\x80-\xFF]', '', text)
            cleaned = re.sub(r'[^A-Za-z0-9 \.,!?\'-]', ' ', cleaned)
            cleaned = re.sub(r'\s+', ' ', cleaned).strip()
            if cleaned:
                blocks.append({'offset': offset, 'english': cleaned})
    blocks.sort(key=lambda x: x['offset'])
    return blocks

def encode_korean(text):
    """한글 텍스트 → ROM 바이트열 (음절 인덱스 기반)"""
    result = bytearray()
    for ch in text:
        if '가' <= ch <= '힣':
            if ch in SYLL_TO_IDX:
                result.append(0x80 + SYLL_TO_IDX[ch])
            # else: 지원하지 않는 음절 → 건너뜀
        elif ch == ' ':
            result.append(0x20)
        elif ch == '\n':
            result.append(0x12)
            result.append(0x11)
        elif ch.isascii() and 0x21 <= ord(ch) <= 0x7E:
            rb = ord(ch) - 6
            if rb >= 0x1A:
                result.append(rb)
        # 기타 문자 건너뜀
    return bytes(result)

def is_valid_text_at(rom, offset, min_len=3):
    """오프셋이 실제 텍스트 위치인지 검증"""
    if offset + min_len >= len(rom):
        return False
    count = 0
    for i in range(min(20, len(rom)-offset)):
        b = rom[offset+i]
        if b == 0x00:
            break
        if 0x1A <= b <= 0x7E or b == 0x20:
            count += 1
        elif b < 0x20:  # control code
            pass
        else:
            return False  # 비정상 바이트
    return count >= min_len

blocks = parse_text_blocks(content)
print(f"텍스트 블록: {len(blocks)}개")

replaced = 0
skipped_no_trans = 0
skipped_no_fit = 0
skipped_invalid = 0

for block in blocks:
    offset = block['offset']
    english = block['english']
    korean = cache.get(english, '')

    if not korean:
        skipped_no_trans += 1
        continue

    if not is_valid_text_at(rom, offset):
        skipped_invalid += 1
        continue

    kor_bytes = encode_korean(korean)
    orig_len = len(english)

    if not kor_bytes:
        skipped_no_fit += 1
        continue

    if len(kor_bytes) > orig_len:
        kor_bytes = kor_bytes[:orig_len]

    if not kor_bytes:
        skipped_no_fit += 1
        continue

    # 기록
    rom[offset:offset+len(kor_bytes)] = kor_bytes
    rom[offset+len(kor_bytes)] = 0x00
    replaced += 1

print(f"삽입 완료: {replaced}개")
print(f"  번역 없음: {skipped_no_trans}, 위치 불일치: {skipped_invalid}, 공간 부족: {skipped_no_fit}")

# ============================================================
# 6. ROM 저장
# ============================================================
with open(OUT_ROM, 'wb') as f:
    f.write(rom)

print(f"\n=== 완료 ===")
print(f"출력: {OUT_ROM}")
print(f"  훅    @ ROM 0x{HOOK_ROM_OFF:06X}: {bytes(hook_patch).hex()}")
print(f"  트램  @ ROM 0x{TRAMPOLINE_ROM_OFF:06X}: {bytes(trampoline[:8]).hex()}...")
print(f"  글리프 @ ROM 0x{GLYPH_ROM_OFF:06X}: {len(glyph_data)} bytes")
print(f"  너비  @ ROM 0x{WIDTH_TABLE1_OFF:06X} + 0x{WIDTH_TABLE2_OFF:06X}: tile 0x80-0xFE → {KOREAN_WIDTH}px")
print(f"\nmGBA 테스트: ZOE_Korean_v5.gba를 mGBA로 실행하고 New Game 시작")
