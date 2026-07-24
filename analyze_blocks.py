import sys, io, json, re
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

with open('extracted_text.txt', encoding='utf-8-sig') as f:
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
            blocks.append({'offset': offset, 'text': cleaned[:60]})

blocks.sort(key=lambda x: x['offset'])
print(f'Total blocks: {len(blocks)}')
print(f'Offset range: 0x{blocks[0]["offset"]:06X} ~ 0x{blocks[-1]["offset"]:06X}')
print()
print('First 20 blocks:')
for b in blocks[:20]:
    print(f'  0x{b["offset"]:06X}: {b["text"]}')
print()
early = [b for b in blocks if b['offset'] < 0x100000]
print(f'Blocks in 0x000000-0x100000: {len(early)}')
for b in early[:10]:
    print(f'  0x{b["offset"]:06X}: {b["text"]}')
