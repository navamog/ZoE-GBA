"""
ZOE GBA 한글 패치 빌더 v3 - 완전히 새로 작성
핵심 수정:
  038AC 함수 분석 결과:
    - r0(반환값) = font_base + tile_id * 32  (glyph 픽셀 데이터 포인터)
    - 호출자가 이 포인터에서 직접 픽셀 읽음
    - IWRAM은 캐시 메타데이터용 (픽셀 저장 아님)
  한글 경로:
    - r0 = GLYPH_GBA + (tile_id-0x80)*32 반환
    - IWRAM 복사 불필요
    - BX LR로 바로 리턴
"""
import struct, os, sys, io, json, re
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

ROM_PATH  = r"D:\Works\zoe\Zone of the Enders - The Fist of Mars (USA).gba"
OUT_ROM   = r"D:\Works\zoe\ZOE_Korean3.gba"
GLYPH_BIN = r"D:\Works\zoe\korean_glyphs2.bin"  # gen_font2.py 출력

TRAMPOLINE_ROM_OFF = 0x78C540
GLYPH_ROM_OFF      = 0x78C570   # 트램폴린(44바이트) + 4바이트 패딩 후
TRAMPOLINE_GBA     = 0x08000000 + TRAMPOLINE_ROM_OFF
GLYPH_GBA          = 0x08000000 + GLYPH_ROM_OFF

HOOK_ROM_OFF       = 0x038AC     # 훅 주소 (8바이트 교체)
MAX_SYLLABLES      = 127
ENGLISH_RESUME_GBA = 0x080038B5  # 원본 함수 038AC 이후 (038B4+1, Thumb)

# ============================================================
# 1. 트램폴린 (44 bytes)
# ============================================================
# 진입: r0=slot_index, r1=tile_id
#
# 한글 타일 (0x80~0xFE) 처리:
#   038AC 함수는 font_base + tile_id * 32 를 r0로 반환하고 BX LR
#   → 우리도 동일: r0 = GLYPH_GBA + (tile_id-0x80)*32, BX LR
#
# 영어 타일 처리:
#   038AC의 첫 8바이트(우리가 덮어쓴 부분)를 재현한 뒤 038B4로 점프
#   (038B4 이후 원본 코드 그대로 실행)
#
# 레이아웃:
# +00: MOV r2, r1          ; r2 = tile_id
# +02: SUB r2, #0x80       ; r2 = tile_id - 0x80
# +04: CMP r2, #0x7E
# +06: BHI → +18           ; 0x7E 초과 = 영어 경로
# +08: [한글] LSL r2,r2,#5 ; r2 = (tile_id-0x80)*32
# +0A: LDR r0,[PC,#4]     → pool@+10 = GLYPH_GBA
# +0C: ADD r0, r2, r0      ; r0 = GLYPH_GBA + offset
# +0E: BX lr               ; 호출자로 리턴 (r0 = glyph 데이터 주소)
# +10: [pool: GLYPH_GBA]
# +14: 00 00 padding
# +16: 00 00 padding
# +18: [영어] PUSH {r4,r5,lr}  ; 원본 038AC +00
# +1A: MOV r4, r0              ; 원본 038AC +02
# +1C: LSL r4, r4, #0x18       ; 원본 038AC +04
# +1E: LSL r1, r1, #0x10       ; 원본 038AC +06
# +20: LDR r0,[PC,#4]         → pool@+28 = ENGLISH_RESUME_GBA
# +22: BX r0                   ; 038B4로 점프
# +24: 00 00 padding
# +26: 00 00 padding
# +28: [pool: ENGLISH_RESUME_GBA]
# 총 0x2C = 44 bytes

def u32le(v):
    return [(v>>0)&0xFF, (v>>8)&0xFF, (v>>16)&0xFF, (v>>24)&0xFF]

# BHI offset 검증:
# +06에서 BHI, target=+18, PC_after=+08
# offset = (+18 - +08) / 2 = 8
bhi_offset = (0x18 - 0x08) // 2
assert bhi_offset == 8, f"BHI offset={bhi_offset}"

# LDR r0,[PC,#4] at +0A 검증:
# PC = TRAMPOLINE_ROM_OFF+0x0A+4 = TRAMPOLINE_ROM_OFF+0x0E
# aligned = TRAMPOLINE_ROM_OFF+0x0C (if 4-aligned)
# = 0x78C540+0x0C = 0x78C54C → pool = 0x78C54C+4 = 0x78C550 = +0x10 ✓
# (단 0x78C540이 4바이트 정렬되어야 함: 0x78C540 % 4 = 0 ✓)

# LDR r0,[PC,#4] at +20 검증:
# PC = TRAMPOLINE_ROM_OFF+0x20+4 = TRAMPOLINE_ROM_OFF+0x24
# aligned = +0x24 → pool = +0x24+4 = +0x28 ✓

trampoline = bytearray([
    # +00: 한글 타일 체크
    0x0A, 0x1C,              # MOV r2, r1
    0x80, 0x3A,              # SUBS r2, #0x80
    0x7E, 0x2A,              # CMP r2, #0x7E
    bhi_offset, 0xD8,        # BHI → +18 (영어 경로)
    # +08: 한글 경로 (r0 = GLYPH_GBA + (tile-0x80)*32, BX lr)
    0x52, 0x01,              # LSLS r2, r2, #5
    0x01, 0x48,              # LDR r0, [PC, #4]  → pool@+10
    0x10, 0x18,              # ADDS r0, r2, r0
    0x70, 0x47,              # BX lr
    # +10: pool (GLYPH_GBA)
    *u32le(GLYPH_GBA),
    # +14: padding
    0x00, 0x00,
    0x00, 0x00,
    # +18: 영어 경로 (원본 038AC 첫 8바이트 재현 후 038B4로 점프)
    0x30, 0xB5,              # PUSH {r4, r5, lr}   (원본 +00)
    0x04, 0x1C,              # ADDS r4, r0, #0     (원본 +02: MOV r4,r0)
    0x24, 0x06,              # LSLS r4, r4, #0x18  (원본 +04)
    0x09, 0x04,              # LSLS r1, r1, #0x10  (원본 +06)
    0x01, 0x48,              # LDR r0, [PC, #4]   → pool@+28
    0x00, 0x47,              # BX r0              → 038B4
    # +24: padding
    0x00, 0x00,
    0x00, 0x00,
    # +28: pool (ENGLISH_RESUME_GBA)
    *u32le(ENGLISH_RESUME_GBA),
])
assert len(trampoline) == 0x2C, f"트램폴린 크기 오류: {len(trampoline)}"
print(f"트램폴린: {len(trampoline)} bytes")

# ============================================================
# 2. 훅 패치 (8 bytes at 038AC)
# ============================================================
TRAMPOLINE_THUMB = TRAMPOLINE_GBA | 1
hook_patch = bytearray([
    0x00, 0x48,              # LDR r0, [PC, #0]
    0x00, 0x47,              # BX r0
    *u32le(TRAMPOLINE_THUMB),
])
assert len(hook_patch) == 8

# ============================================================
# 3. 글리프 데이터 로드 (gen_font2.py 출력)
# ============================================================
with open(GLYPH_BIN, 'rb') as f:
    glyph_data = f.read()
assert len(glyph_data) == MAX_SYLLABLES * 32, f"글리프 크기 오류: {len(glyph_data)}"
print(f"글리프: {len(glyph_data)} bytes ({MAX_SYLLABLES} 음절 × 32 bytes)")

# GLYPH_ROM_OFF 공간 확인
glyph_end = GLYPH_ROM_OFF + len(glyph_data)
tramp_end = TRAMPOLINE_ROM_OFF + len(trampoline)
print(f"트램폴린: ROM 0x{TRAMPOLINE_ROM_OFF:06X} ~ 0x{tramp_end:06X}")
print(f"글리프:   ROM 0x{GLYPH_ROM_OFF:06X} ~ 0x{glyph_end:06X}")
assert GLYPH_ROM_OFF >= tramp_end, "글리프 영역이 트램폴린과 겹침!"

# ============================================================
# 4. ROM 패치 적용
# ============================================================
with open(ROM_PATH, 'rb') as f:
    rom = bytearray(f.read())

orig_hook = rom[HOOK_ROM_OFF:HOOK_ROM_OFF+4]
print(f"\n훅 위치 ROM[{HOOK_ROM_OFF:06X}]: {orig_hook.hex()} (기대: 30 b5 04 1c)")

# 영역 체크
def check_area(rom, start, size, name):
    area = rom[start:start+size]
    non_ff = sum(1 for b in area if b != 0xFF)
    if non_ff > 0:
        print(f"  경고: {name} 영역에 비FF 바이트 {non_ff}개")
    else:
        print(f"  {name} 영역: 클린 (모두 0xFF)")

check_area(rom, TRAMPOLINE_ROM_OFF, len(trampoline) + 4, "트램폴린")
check_area(rom, GLYPH_ROM_OFF, len(glyph_data), "글리프")

rom[HOOK_ROM_OFF       : HOOK_ROM_OFF+8]                     = hook_patch
rom[TRAMPOLINE_ROM_OFF : TRAMPOLINE_ROM_OFF+len(trampoline)] = trampoline
rom[GLYPH_ROM_OFF      : GLYPH_ROM_OFF+len(glyph_data)]     = glyph_data

# ============================================================
# 5. 너비 테이블 패치 (한글 0x80-0xFE → width 12)
# ============================================================
WIDTH_TABLE_OFF = 0x553676
for tile in range(0x80, 0xFF):
    rom[WIDTH_TABLE_OFF + tile] = 12
print("너비 테이블: tile 0x80-0xFE → 12px")

# ============================================================
# 6. 한글 텍스트 삽입
# ============================================================
with open(r"D:\Works\zoe\syllable_index.json", encoding='utf-8') as f:
    syll_dict = json.load(f)
SYLL_TO_IDX = {k: v for k, v in syll_dict.items() if v < MAX_SYLLABLES}

cache = {}
if os.path.exists(r"D:\Works\zoe\translation_cache.json"):
    with open(r"D:\Works\zoe\translation_cache.json", encoding='utf-8') as f:
        cache = json.load(f)
print(f"번역 캐시: {len(cache)}개")

with open(r"D:\Works\zoe\extracted_text.txt", encoding='utf-8-sig') as f:
    content = f.read()

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

def encode_korean(text):
    result = bytearray()
    for ch in text:
        if '가' <= ch <= '힣':
            if ch not in SYLL_TO_IDX: continue
            result.append(0x80 + SYLL_TO_IDX[ch])
        elif ch == ' ':
            result.append(0x20)
        elif ch == '\n':
            result.append(0x12); result.append(0x11)
        elif ch.isascii() and 0x20 <= ord(ch) <= 0x7E:
            rb = ord(ch) - 6
            if rb >= 0x20:
                result.append(rb)
    return bytes(result)

VALID_TEXT_BYTES = set(range(0x1A, 0x79)) | set(range(0x00, 0x10))
def is_valid_text_block(r, offset, length):
    if offset + length + 1 >= len(r): return False
    if length < 3: return False
    valid = 0
    for i in range(min(length, 20)):
        b = r[offset + i]
        if b in VALID_TEXT_BYTES: valid += 1
        elif b == 0x00: break
        else: return False
    return valid >= 2

replaced = 0
for block in blocks:
    offset = block['offset']
    english = block['english']
    korean = cache.get(english, '')
    if not korean: continue
    orig_size = len(english)
    if not is_valid_text_block(rom, offset, orig_size): continue
    kor_bytes = encode_korean(korean)
    if len(kor_bytes) > orig_size:
        kor_bytes = kor_bytes[:orig_size]
    if not kor_bytes: continue
    rom[offset:offset+len(kor_bytes)] = kor_bytes
    rom[offset+len(kor_bytes)] = 0x00
    replaced += 1

with open(OUT_ROM, 'wb') as f:
    f.write(rom)

print(f"텍스트 삽입: {replaced}개")
print(f"\n출력: {OUT_ROM}")
print(f"  훅    @ 0x{HOOK_ROM_OFF:06X}: {bytes(hook_patch).hex()}")
print(f"  트램  @ 0x{TRAMPOLINE_ROM_OFF:06X}: {bytes(trampoline[:8]).hex()}...")
print(f"  글리프 @ 0x{GLYPH_ROM_OFF:06X}")
