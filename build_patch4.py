"""
ZOE GBA 한글 패치 빌더 v4
build_patch3.py에서 BHI 오프셋 버그 수정:
  문제: bhi_offset = (0x18-0x08)//2 = 8  (PC를 +08로 잘못 계산)
  수정: bhi_offset = (0x18-0x0A)//2 = 7  (Thumb PC = instruction_addr+4 = +0A)
  영향: offset=8이면 PUSH{r4,r5,lr}를 건너뜀
        → 원본 038AC의 POP이 스택 손상값을 읽음
        → BX r1로 쓰레기 주소 점프 → 크래시 (인트로로 리셋)
"""
import struct, os, sys, io, json, re
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

ROM_PATH  = r"D:\Works\zoe\Zone of the Enders - The Fist of Mars (USA).gba"
OUT_ROM   = r"D:\Works\zoe\ZOE_Korean4.gba"
GLYPH_BIN = r"D:\Works\zoe\korean_glyphs2.bin"

TRAMPOLINE_ROM_OFF = 0x78C540
GLYPH_ROM_OFF      = 0x78C570   # 트램폴린(44바이트) + 패딩 후
TRAMPOLINE_GBA     = 0x08000000 + TRAMPOLINE_ROM_OFF
GLYPH_GBA          = 0x08000000 + GLYPH_ROM_OFF

HOOK_ROM_OFF       = 0x038AC    # 훅 주소 (8바이트 교체)
MAX_SYLLABLES      = 127
ENGLISH_RESUME_GBA = 0x080038B5  # 038B4+1 (Thumb)

def u32le(v):
    return [(v>>0)&0xFF, (v>>8)&0xFF, (v>>16)&0xFF, (v>>24)&0xFF]

# ============================================================
# BHI 오프셋 계산 (핵심 수정)
# ============================================================
# BHI 명령어 위치: trampoline +06
# Thumb PC = instruction_addr + 4
# instruction_addr (byte offset) = +06
# PC (byte offset)               = +06 + 4 = +0A
# 목표 (byte offset)             = +18  (PUSH {r4,r5,lr} 위치)
# imm8 = (0x18 - 0x0A) / 2 = 7
bhi_offset = (0x18 - 0x0A) // 2
assert bhi_offset == 7, f"BHI 오프셋 오류: {bhi_offset}"

# LDR r0,[PC,#4] 풀 주소 검증 (at trampoline +0A)
# PC = +0A + 4 = +0E, aligned = +0C → pool = +0C + 4 = +10 ✓
# LDR r0,[PC,#4] 풀 주소 검증 (at trampoline +20)
# PC = +20 + 4 = +24, aligned = +24 → pool = +24 + 4 = +28 ✓

# ============================================================
# 트램폴린 (44 bytes = 0x2C)
# ============================================================
# 진입: r0=slot_index, r1=tile_id  (038AC 시그니처 그대로)
#
# 한글 타일 (0x80~0xFE):
#   r0 = GLYPH_GBA + (tile_id-0x80)*32  → BX lr (직접 ROM 픽셀 포인터 반환)
#   블리터가 r7=[r0]에서 바로 픽셀 읽음 (ldrb r0,[r7] @ 0x80035BE)
#
# 영어 타일:
#   원본 038AC 첫 4명령어 재현 후 038B4로 점프 (원본 계속 실행)
#   PUSH/POP 쌍이 정확히 맞아야 스택 보존
#
# 레이아웃:
# +00: ADDS r2, r1, #0    ; r2 = tile_id
# +02: SUBS r2, #0x80     ; r2 = tile_id - 0x80
# +04: CMP r2, #0x7E
# +06: BHI → +18          ; >0x7E = 영어/비한글
# +08: LSLS r2, r2, #5   ; r2 = (tile_id-0x80)*32
# +0A: LDR r0,[PC,#4]    → pool@+10 = GLYPH_GBA
# +0C: ADDS r0, r2, r0   ; r0 = GLYPH_GBA + offset
# +0E: BX lr             ; 호출자로 리턴
# +10: [pool: GLYPH_GBA]
# +14: 00 00 padding
# +16: 00 00 padding
# +18: PUSH {r4,r5,lr}   ; 원본 038AC +00
# +1A: ADDS r4, r0, #0   ; 원본 038AC +02
# +1C: LSLS r4, r4, #0x18 ; 원본 038AC +04
# +1E: LSLS r1, r1, #0x10 ; 원본 038AC +06
# +20: LDR r0,[PC,#4]   → pool@+28 = ENGLISH_RESUME_GBA
# +22: BX r0            → 038B4 (나머지 원본 코드 실행)
# +24: 00 00 padding
# +26: 00 00 padding
# +28: [pool: ENGLISH_RESUME_GBA]
# 총 0x2C = 44 bytes

trampoline = bytearray([
    # +00: 한글 타일 체크
    0x0A, 0x1C,              # ADDS r2, r1, #0    (MOV r2, r1)
    0x80, 0x3A,              # SUBS r2, #0x80
    0x7E, 0x2A,              # CMP r2, #0x7E
    bhi_offset, 0xD8,        # BHI → +18 (영어 경로)  [offset=7, 올바른 값]
    # +08: 한글 경로
    0x52, 0x01,              # LSLS r2, r2, #5
    0x01, 0x48,              # LDR r0, [PC, #4]   → pool@+10
    0x10, 0x18,              # ADDS r0, r2, r0
    0x70, 0x47,              # BX lr
    # +10: pool (GLYPH_GBA)
    *u32le(GLYPH_GBA),
    # +14: padding
    0x00, 0x00,
    0x00, 0x00,
    # +18: 영어 경로 (원본 038AC 첫 4명령어 재현 후 038B4로 점프)
    0x30, 0xB5,              # PUSH {r4, r5, lr}   (원본 +00)
    0x04, 0x1C,              # ADDS r4, r0, #0     (원본 +02)
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
print(f"트램폴린: {len(trampoline)} bytes (BHI offset={bhi_offset})")

# ============================================================
# 훅 패치 (8 bytes at 038AC)
# ============================================================
TRAMPOLINE_THUMB = TRAMPOLINE_GBA | 1
hook_patch = bytearray([
    0x00, 0x48,              # LDR r0, [PC, #0]  → pool@038B0
    0x00, 0x47,              # BX r0             → TRAMPOLINE_THUMB
    *u32le(TRAMPOLINE_THUMB),
])
assert len(hook_patch) == 8

# ============================================================
# 글리프 데이터 로드
# ============================================================
with open(GLYPH_BIN, 'rb') as f:
    glyph_data = f.read()
assert len(glyph_data) == MAX_SYLLABLES * 32, f"글리프 크기 오류: {len(glyph_data)}"
print(f"글리프: {len(glyph_data)} bytes ({MAX_SYLLABLES} 음절 × 32 bytes)")

tramp_end = TRAMPOLINE_ROM_OFF + len(trampoline)
glyph_end = GLYPH_ROM_OFF + len(glyph_data)
assert GLYPH_ROM_OFF >= tramp_end, "글리프 영역이 트램폴린과 겹침!"
print(f"트램폴린: ROM 0x{TRAMPOLINE_ROM_OFF:06X}~0x{tramp_end:06X}")
print(f"글리프:   ROM 0x{GLYPH_ROM_OFF:06X}~0x{glyph_end:06X}")

# ============================================================
# ROM 패치 적용
# ============================================================
with open(ROM_PATH, 'rb') as f:
    rom = bytearray(f.read())

orig = rom[HOOK_ROM_OFF:HOOK_ROM_OFF+8]
print(f"\n훅 위치 ROM[{HOOK_ROM_OFF:06X}]: {orig.hex()}")

def check_area(rom, start, size, name):
    area = rom[start:start+size]
    non_ff = sum(1 for b in area if b != 0xFF)
    status = f"클린 (모두 0xFF)" if non_ff == 0 else f"경고: 비FF 바이트 {non_ff}개"
    print(f"  {name}: {status}")

check_area(rom, TRAMPOLINE_ROM_OFF, len(trampoline) + 4, "트램폴린 영역")
check_area(rom, GLYPH_ROM_OFF, len(glyph_data), "글리프 영역")

rom[HOOK_ROM_OFF         : HOOK_ROM_OFF+8]                    = hook_patch
rom[TRAMPOLINE_ROM_OFF   : TRAMPOLINE_ROM_OFF+len(trampoline)] = trampoline
rom[GLYPH_ROM_OFF        : GLYPH_ROM_OFF+len(glyph_data)]    = glyph_data

# ============================================================
# 너비 테이블 패치 (한글 0x80-0xFE → width 12)
# ============================================================
WIDTH_TABLE_OFF = 0x553676
for tile in range(0x80, 0xFF):
    rom[WIDTH_TABLE_OFF + tile] = 12
print("너비 테이블: tile 0x80~0xFE → 12px")

# ============================================================
# 한글 텍스트 삽입
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
print(f"  트램  @ 0x{TRAMPOLINE_ROM_OFF:06X}: bhi_offset={bhi_offset}")
print(f"  글리프 @ 0x{GLYPH_ROM_OFF:06X}: {len(glyph_data)} bytes")
