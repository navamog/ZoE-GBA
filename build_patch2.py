"""
ZOE GBA 한글 패치 빌더 v2
- 글리프: gen_font2.py 생성 korean_glyphs2.bin (Galmuri11 BDF, 픽셀 퍼펙트)
- 훅/트램폴린 구조는 build_patch.py v4와 동일
- 기존 파일 수정 없이 독립 실행
"""
import struct, os, sys, io, json
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

ROM_PATH   = r"D:\Works\zoe\Zone of the Enders - The Fist of Mars (USA).gba"
OUT_ROM    = r"D:\Works\zoe\ZOE_Korean2.gba"
GLYPH_BIN  = r"D:\Works\zoe\korean_glyphs2.bin"

TRAMPOLINE_ROM_OFF = 0x78C540
GLYPH_ROM_OFF      = 0x78C590
TRAMPOLINE_GBA     = 0x08000000 + TRAMPOLINE_ROM_OFF
GLYPH_GBA          = 0x08000000 + GLYPH_ROM_OFF

HOOK_ROM_OFF       = 0x038AC
MAX_SYLLABLES      = 127
ENGLISH_RESUME_GBA = 0x080038B5
IWRAM_BASE         = 0x03003320

# ============================================================
# 1. 글리프 데이터 로드 (gen_font2.py 출력)
# ============================================================
with open(GLYPH_BIN, 'rb') as f:
    glyph_data = f.read()

assert len(glyph_data) == MAX_SYLLABLES * 32, \
    f"글리프 데이터 크기 오류: {len(glyph_data)} (기대: {MAX_SYLLABLES * 32})"
print(f"글리프 로드: {len(glyph_data)} bytes ({MAX_SYLLABLES} 음절)")

# ============================================================
# 2. 트램폴린 (build_patch.py v4와 동일)
# ============================================================
def u32le(v):
    return [(v>>0)&0xFF, (v>>8)&0xFF, (v>>16)&0xFF, (v>>24)&0xFF]

trampoline = bytearray([
    # +00: 한글 타일 체크 (tile 0x80-0xFE)
    0x0A, 0x1C,  # MOV r2, r1          ; r2 = tile_id
    0x80, 0x3A,  # SUB r2, #0x80       ; r2 = tile_id - 0x80 (glyph index)
    0x7E, 0x2A,  # CMP r2, #0x7E
    0x17, 0xD8,  # BHI → +38 (english)
    # +08: 한글 경로
    0x30, 0xB5,  # PUSH {r4,r5,lr}
    0x03, 0x1C,  # MOV r3, r0          ; r3 = slot (이미 바이트 오프셋 = index*32)
    0x00, 0x00,  # NOP (LSL r0,r0,#0)  ; [수정] slot은 이미 바이트 오프셋 → 곱하기 불필요
    0x08, 0x48,  # LDR r0, [PC, #32]  → pool1@+30 = IWRAM_BASE
    0x1B, 0x18,  # ADD r3, r3, r0      ; r3 = IWRAM_BASE + slot (정확한 목적지)
    0x08, 0xB4,  # PUSH {r3}           ; dest 저장
    0x52, 0x01,  # LSL r2, r2, #5      ; r2 = glyph_index * 32 (ROM 오프셋)
    0x07, 0x48,  # LDR r0, [PC, #28]  → pool2@+34 = GLYPH_GBA
    0x12, 0x18,  # ADD r2, r2, r0      ; r2 = GLYPH_GBA + glyph_index*32 (소스)
    0x30, 0xCA,  # LDMIA r2!, {r4,r5}
    0x30, 0xC3,  # STMIA r3!, {r4,r5}
    0x30, 0xCA,  # LDMIA r2!, {r4,r5}
    0x30, 0xC3,  # STMIA r3!, {r4,r5}
    0x30, 0xCA,  # LDMIA r2!, {r4,r5}
    0x30, 0xC3,  # STMIA r3!, {r4,r5}
    0x30, 0xCA,  # LDMIA r2!, {r4,r5}
    0x30, 0xC3,  # STMIA r3!, {r4,r5}
    0x01, 0xBC,  # POP {r0}            ; r0 = dest (IWRAM 주소 반환)
    0x30, 0xBD,  # POP {r4,r5,pc}
    0x00, 0x00,  # padding
    # pool1 @ +30
    *u32le(IWRAM_BASE),
    # pool2 @ +34
    *u32le(GLYPH_GBA),
    # +38: 영어 경로 (원본 038AC 로직 재현)
    0x30, 0xB5,  # PUSH {r4,r5,lr}
    0x04, 0x1C,  # MOV r4, r0
    0x24, 0x06,  # LSL r4, r4, #24
    0x09, 0x04,  # LSL r1, r1, #16
    0x01, 0x48,  # LDR r0, [PC, #4]   → pool3@+48
    0x00, 0x47,  # BX r0
    0x00, 0x00,  # padding
    0x00, 0x00,  # padding
    # pool3 @ +48
    *u32le(ENGLISH_RESUME_GBA),
])
assert len(trampoline) == 0x4C, f"트램폴린 크기 오류: {len(trampoline)}"
print(f"트램폴린: {len(trampoline)} bytes")

# ============================================================
# 3. 훅 패치
# ============================================================
TRAMPOLINE_THUMB = TRAMPOLINE_GBA | 1
hook_patch = bytearray([
    0x00, 0x48,
    0x00, 0x47,
    *u32le(TRAMPOLINE_THUMB),
])

# ============================================================
# 4. ROM 패치 적용
# ============================================================
with open(ROM_PATH, 'rb') as f:
    rom = bytearray(f.read())

orig_hook = rom[HOOK_ROM_OFF:HOOK_ROM_OFF+4]
print(f"훅 위치 ROM[{HOOK_ROM_OFF:06X}]: {orig_hook.hex()} (기대: 30 b5 04 1c)")

# 트램폴린 영역 사용 여부 확인
area = rom[TRAMPOLINE_ROM_OFF:TRAMPOLINE_ROM_OFF+0x100]
non_ff = sum(1 for b in area if b != 0xFF)
if non_ff > 0:
    print(f"  경고: 트램폴린 영역에 비FF 바이트 {non_ff}개 존재")

rom[HOOK_ROM_OFF         : HOOK_ROM_OFF+8]         = hook_patch
rom[TRAMPOLINE_ROM_OFF   : TRAMPOLINE_ROM_OFF+len(trampoline)] = trampoline
rom[GLYPH_ROM_OFF        : GLYPH_ROM_OFF+len(glyph_data)]     = glyph_data

# ============================================================
# 5. 한글 텍스트 삽입
# ============================================================
with open(r"D:\Works\zoe\syllable_index.json", encoding='utf-8') as f:
    syll_dict = json.load(f)
SYLL_TO_IDX = {k: v for k, v in syll_dict.items() if v < MAX_SYLLABLES}

cache = {}
cache_path = r"D:\Works\zoe\translation_cache.json"
if os.path.exists(cache_path):
    with open(cache_path, encoding='utf-8') as f:
        cache = json.load(f)
print(f"번역 캐시: {len(cache)}개")

import re
text_path = r"D:\Works\zoe\extracted_text.txt"
with open(text_path, encoding='utf-8-sig') as f:
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

# ============================================================
# 6. 너비 테이블 패치 (0x553676 + tile_id)
# ============================================================
# 원본: 한글 범위 0x80-0xFE → 모두 width=8 (영어와 동일)
# 수정: Galmuri11 DWIDTH=12에 맞게 width=12로 패치
WIDTH_TABLE_OFF = 0x553676
KOREAN_WIDTH = 12
for tile in range(0x80, 0xFF):
    rom[WIDTH_TABLE_OFF + tile] = KOREAN_WIDTH
print(f"너비 테이블 패치: tile 0x80-0xFE → width={KOREAN_WIDTH}")

with open(OUT_ROM, 'wb') as f:
    f.write(rom)

print(f"한글 텍스트 삽입: {replaced}개")
print(f"\nROM 출력: {OUT_ROM}")
print(f"  훅    @ 0x{HOOK_ROM_OFF:06X}: {bytes(hook_patch).hex()}")
print(f"  트램  @ 0x{TRAMPOLINE_ROM_OFF:06X}")
print(f"  글리프 @ 0x{GLYPH_ROM_OFF:06X}: {len(glyph_data)} bytes (Galmuri11)")
