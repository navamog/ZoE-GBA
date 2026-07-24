"""
진단 스크립트: 두 가지 확인
1. 너비 테이블 0x80-0xFE 범위 값 확인
2. 진단용 트램폴린 빌드 (한글 → 영어 타일로 대체)
   한글 타일을 전부 타일 0x3B('A'에 해당)로 렌더링
   → IWRAM 복사 코드가 문제인지 확인
"""
import sys, io, json
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

ROM_PATH = r"D:\Works\zoe\Zone of the Enders - The Fist of Mars (USA).gba"
OUT_ROM  = r"D:\Works\zoe\ZOE_Diag.gba"

with open(ROM_PATH, 'rb') as f:
    rom = bytearray(f.read())

# ============================================================
# 1. 너비 테이블 확인
# ============================================================
# 너비 함수 0x03900이 ROM 0x08553676 (= ROM offset 0x553676)의 테이블 사용
WIDTH_TABLE_OFF = 0x553676
print("=== 너비 테이블 (tile 0x78-0xFF) ===")
for tile in range(0x78, 0x100):
    off = WIDTH_TABLE_OFF + tile
    if off < len(rom):
        val = rom[off]
        if tile >= 0x7F:
            print(f"  tile 0x{tile:02X} → width={val} (0x{val:02X})")

# ============================================================
# 2. 진단 트램폴린: 한글 타일 → 타일 0x3B로 대체 (IWRAM 복사 없음)
# ============================================================
# 레이아웃 (TRAMPOLINE_ROM_OFF = 0x78C540):
# +00: MOV r2, r1
# +02: SUB r2, #0x80
# +04: CMP r2, #0x7E
# +06: BHI → +1C (english_path)
# +08: [한글 경로] PUSH {r4,r5,lr}
# +0A: MOV r4, r0        ; r4 = slot
# +0C: LSL r4, r4, #24
# +0E: MOV r1, #0x3B     ; 더미 타일 (영어 'A')
# +10: LSL r1, r1, #16
# +12: LDR r0, [PC,#4]   → pool1@+18 = ENGLISH_RESUME_GBA
# +14: BX r0             → 038B4
# +16: 00 00  (패딩)
# +18: [pool1] = 0x080038B5
# +1C: [영어 경로] PUSH {r4,r5,lr}
# +1E: MOV r4, r0
# +20: LSL r4, r4, #24
# +22: LSL r1, r1, #16
# +24: LDR r0, [PC,#4]   → pool2@+2C = ENGLISH_RESUME_GBA
# +26: BX r0
# +28: 00 00  (패딩)
# +2A: 00 00  (패딩)
# +2C: [pool2] = 0x080038B5
# 총 0x30 = 48 bytes

TRAMPOLINE_ROM_OFF = 0x78C540
TRAMPOLINE_GBA     = 0x08000000 + TRAMPOLINE_ROM_OFF
HOOK_ROM_OFF       = 0x038AC
ENGLISH_RESUME_GBA = 0x080038B5

def u32le(v):
    return [(v>>0)&0xFF, (v>>8)&0xFF, (v>>16)&0xFF, (v>>24)&0xFF]

# BHI offset 검증:
# +06에서 BHI: target=+1C, PC+4=+0A, diff=(0x1C-0x0A)/2=9=0x09
bhi_offset = (0x1C - 0x0A) // 2
print(f"\nBHI offset: {bhi_offset} (기대: 9)")

# LDR r0,[PC,#4] at +12 검증:
# PC = TRAMPOLINE_GBA+0x12+4 = TRAMPOLINE_GBA+0x16
# PC_aligned = TRAMPOLINE_GBA+0x14 (if TRAMPOLINE_GBA is 4-byte aligned)
# ... actually PC AND NOT 3
pc_12 = TRAMPOLINE_GBA + 0x12 + 4  # = TRAMPOLINE_GBA + 0x16
pc_12_aligned = pc_12 & ~3
pool1_addr = pc_12_aligned + 4  # imm8=1, offset=4
pool1_off = pool1_addr - 0x08000000
print(f"LDR@+12: PC_aligned=0x{pc_12_aligned:08X}, pool1=0x{pool1_addr:08X} (ROM+0x{pool1_off:X})")
print(f"  기대: ROM+0x{TRAMPOLINE_ROM_OFF+0x18:X}")

# LDR r0,[PC,#4] at +24 검증:
pc_24 = TRAMPOLINE_GBA + 0x24 + 4
pc_24_aligned = pc_24 & ~3
pool2_addr = pc_24_aligned + 4
pool2_off = pool2_addr - 0x08000000
print(f"LDR@+24: PC_aligned=0x{pc_24_aligned:08X}, pool2=0x{pool2_addr:08X} (ROM+0x{pool2_off:X})")
print(f"  기대: ROM+0x{TRAMPOLINE_ROM_OFF+0x2C:X}")

trampoline = bytearray([
    # +00: 한글 체크 (tile 0x80-0xFE)
    0x0A, 0x1C,  # MOV r2, r1
    0x80, 0x3A,  # SUB r2, #0x80
    0x7E, 0x2A,  # CMP r2, #0x7E
    bhi_offset, 0xD8,  # BHI → +1C (english_path)
    # +08: 한글 경로 (타일 0x3B로 대체)
    0x30, 0xB5,  # PUSH {r4,r5,lr}
    0x04, 0x1C,  # MOV r4, r0
    0x24, 0x06,  # LSL r4, r4, #24
    0x3B, 0x21,  # MOV r1, #0x3B      ; 더미 타일
    0x09, 0x04,  # LSL r1, r1, #16
    0x01, 0x48,  # LDR r0, [PC,#4]    → pool1@+18
    0x00, 0x47,  # BX r0
    0x00, 0x00,  # +16: 패딩
    # +18: pool1 = ENGLISH_RESUME_GBA
    *u32le(ENGLISH_RESUME_GBA),
    # +1C: 영어 경로
    0x30, 0xB5,  # PUSH {r4,r5,lr}
    0x04, 0x1C,  # MOV r4, r0
    0x24, 0x06,  # LSL r4, r4, #24
    0x09, 0x04,  # LSL r1, r1, #16
    0x01, 0x48,  # LDR r0, [PC,#4]    → pool2@+2C
    0x00, 0x47,  # BX r0
    0x00, 0x00,  # +28: 패딩
    0x00, 0x00,  # +2A: 패딩
    # +2C: pool2 = ENGLISH_RESUME_GBA
    *u32le(ENGLISH_RESUME_GBA),
])
assert len(trampoline) == 0x30, f"트램폴린 크기 오류: {len(trampoline)} (기대: 48)"
print(f"\n트램폴린: {len(trampoline)} bytes ✓")

TRAMPOLINE_THUMB = TRAMPOLINE_GBA | 1
hook_patch = bytearray([
    0x00, 0x48,  # LDR r0, [PC, #0]
    0x00, 0x47,  # BX r0
    *u32le(TRAMPOLINE_THUMB),
])

# ROM 패치
orig_hook = rom[HOOK_ROM_OFF:HOOK_ROM_OFF+4]
print(f"훅 위치 ROM[038AC]: {orig_hook.hex()} (기대: 30 b5 04 1c)")

area = rom[TRAMPOLINE_ROM_OFF:TRAMPOLINE_ROM_OFF+0x40]
print(f"트램폴린 영역 비FF: {sum(1 for b in area if b!=0xFF)}개 (기대: 0)")

rom[HOOK_ROM_OFF:HOOK_ROM_OFF+8] = hook_patch
rom[TRAMPOLINE_ROM_OFF:TRAMPOLINE_ROM_OFF+len(trampoline)] = trampoline

with open(OUT_ROM, 'wb') as f:
    f.write(rom)

# ============================================================
# 3. 한글 텍스트 삽입 (번역 캐시 사용)
# ============================================================
import re, os

SYLL_IDX   = r"D:\Works\zoe\syllable_index.json"
TRANS_CACHE= r"D:\Works\zoe\translation_cache.json"
TEXT_FILE  = r"D:\Works\zoe\extracted_text.txt"

with open(SYLL_IDX, encoding='utf-8') as f:
    _all_syll = json.load(f)
SYLL_TO_IDX = {k: v for k, v in _all_syll.items() if v < 127}

cache = {}
if os.path.exists(TRANS_CACHE):
    with open(TRANS_CACHE, encoding='utf-8') as f:
        cache = json.load(f)
print(f"번역 캐시: {len(cache)}개")

with open(TEXT_FILE, encoding='utf-8-sig') as f:
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

with open(OUT_ROM, 'rb') as f:
    rom = bytearray(f.read())

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

print(f"한글 텍스트 삽입: {replaced}개")
print(f"\n출력: {OUT_ROM}")
print("테스트 방법: ZOE_Diag.gba로 뉴 게임 실행")
print("  - 충돌 없으면: v4 트램폴린의 IWRAM 복사 코드가 문제")
print("  - 충돌 있으면: 텍스트 인코딩 자체가 문제 (너비 테이블은 이상 없음)")
