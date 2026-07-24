import sys, io, json, re, struct
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

ROM = r"D:\Works\zoe\Zone of the Enders - The Fist of Mars (USA).gba"
with open(ROM, 'rb') as f:
    rom = f.read()

with open(r'D:\Works\zoe\translation_cache.json', encoding='utf-8') as f:
    cache = json.load(f)

with open(r'D:\Works\zoe\extracted_text.txt', encoding='utf-8-sig') as f:
    content = f.read()

def encode_korean_simple(text, syll_idx):
    result = bytearray()
    for ch in text:
        if '가' <= ch <= '힣':
            idx = syll_idx.get(ch, 0)
            result.append(0x80 | (idx >> 8))
            result.append(idx & 0xFF)
        elif ch == ' ':
            result.append(0x1A)
        elif ch.isascii() and 0x20 <= ord(ch) <= 0x7E:
            rom_byte = ord(ch) - 6
            if rom_byte >= 0x20:
                result.append(rom_byte)
    return bytes(result)

with open(r'D:\Works\zoe\syllable_index.json', encoding='utf-8') as f:
    syll_idx = json.load(f)

# 처음 20개 매칭 블록 디버그
blocks_checked = 0
overflows = 0
for b in content.split('\n[OFFSET:'):
    b = b.lstrip('[OFFSET:').strip()
    if not b: continue
    lines = b.split('\n')
    try:
        offset = int(lines[0].rstrip(']'), 16)
    except:
        continue
    text = '\n'.join(lines[1:]).strip()
    if not text: continue

    cleaned = re.sub(r'[\x00-\x1F\x80-\xFF]', '', text)
    cleaned = re.sub(r'[^A-Za-z0-9 \.,!?\'-]', ' ', cleaned)
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()

    korean = cache.get(cleaned, '')
    if not korean:
        continue

    # 원본 크기 측정
    i = offset
    while i < len(rom) and rom[i] != 0x00:
        if rom[i] <= 0x0F:
            i += 2
        else:
            i += 1
    orig_size = i - offset

    # 한글 인코딩
    kor_bytes = encode_korean_simple(korean, syll_idx)

    blocks_checked += 1
    if len(kor_bytes) > orig_size:
        overflows += 1
        if overflows <= 10:
            # 원본 ROM 바이트 표시
            raw_bytes = rom[offset:offset+min(orig_size,20)]
            print(f"OVERFLOW [{offset:06X}]:")
            print(f"  영문 키: '{cleaned[:40]}'")
            print(f"  한국어: '{korean[:40]}'")
            print(f"  원본 {orig_size}바이트: {raw_bytes.hex()}")
            print(f"  한글 인코딩 {len(kor_bytes)}바이트")
    else:
        if blocks_checked <= 10:
            raw_bytes = rom[offset:offset+min(orig_size,20)]
            print(f"OK [{offset:06X}]: '{cleaned[:30]}' → '{korean[:30]}' ({orig_size}바이트→{len(kor_bytes)}바이트)")

print(f"\n총 검사: {blocks_checked}, overflow: {overflows}, OK: {blocks_checked-overflows}")
