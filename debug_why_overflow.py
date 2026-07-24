import sys, io, json, re
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

OUT_ROM = r"D:\Works\zoe\ZOE_Korean.gba"
with open(OUT_ROM, 'rb') as f:
    rom = bytearray(f.read())

with open(r'D:\Works\zoe\translation_cache.json', encoding='utf-8') as f:
    cache = json.load(f)

with open(r'D:\Works\zoe\syllable_index.json', encoding='utf-8') as f:
    SYLL_TO_IDX = json.load(f)

with open(r'D:\Works\zoe\extracted_text.txt', encoding='utf-8-sig') as f:
    content = f.read()

def encode_korean(text):
    result = bytearray()
    for ch in text:
        if '가' <= ch <= '힣':
            if ch in SYLL_TO_IDX:
                ch_idx = SYLL_TO_IDX[ch]
                result.append(0x80 | ((ch_idx >> 8) & 0x3F))
                result.append(ch_idx & 0xFF)
        elif ch == ' ':
            result.append(0x1A)
        elif ch.isascii() and 0x20 <= ord(ch) <= 0x7E:
            rom_byte = ord(ch) - 6
            if rom_byte >= 0x20:
                result.append(rom_byte)
    return bytes(result)

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
        blocks.append({'offset': offset, 'english': cleaned})

# 처음 10개 overflow/ok 케이스 상세 출력
shown_overflow = 0
shown_ok = 0
for block in blocks:
    offset = block['offset']
    english = block['english']
    korean = cache.get(english, '')
    if not korean:
        continue

    i = offset
    while i < len(rom) and rom[i] != 0x00:
        if rom[i] <= 0x0F:
            i += 2
        else:
            i += 1
    orig_size = i - offset

    kor_bytes = encode_korean(korean)

    if len(kor_bytes) > orig_size:
        if shown_overflow < 5:
            raw = rom[offset:offset+min(20,orig_size+4)]
            print(f"OVERFLOW [{offset:06X}] orig_size={orig_size}, kor={len(kor_bytes)}b")
            print(f"  영문: '{english[:50]}'")
            print(f"  한국: '{korean[:40]}'")
            print(f"  ROM bytes: {raw.hex()}")
        shown_overflow += 1
    else:
        if shown_ok < 5:
            print(f"OK [{offset:06X}] orig_size={orig_size}, kor={len(kor_bytes)}b: '{english[:30]}'")
        shown_ok += 1

print(f"\n총 매칭: {shown_overflow+shown_ok}, OK: {shown_ok}, overflow: {shown_overflow}")
