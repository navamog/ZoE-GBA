import sys, io, re
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

with open('Zone of the Enders - The Fist of Mars (USA).gba', 'rb') as f:
    orig = f.read()
with open('ZOE_Korean.gba', 'rb') as f:
    patched = f.read()

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
            blocks.append({'offset': offset, 'english': cleaned})

blocks.sort(key=lambda x: x['offset'])

# 처음 15개 블록 원본 vs 패치 비교
print('First 15 blocks - original vs patched bytes:')
for b in blocks[:15]:
    off = b['offset']
    orig_bytes = orig[off:off+20]
    patch_bytes = patched[off:off+20]
    changed = orig_bytes != patch_bytes

    # decode orig bytes as text
    decoded = ''
    for by in orig_bytes:
        if 0x1A <= by <= 0x7E:
            decoded += chr(by + 6)
        elif by == 0x00:
            decoded += '[0]'
            break
        elif by < 0x10:
            decoded += f'[{by:02X}]'
        else:
            decoded += '?'

    print(f'0x{off:06X}: {"CHANGED" if changed else "same   "} | orig={orig_bytes[:12].hex()} | dec="{decoded[:20]}"')
    if changed:
        print(f'          patch={patch_bytes[:12].hex()}')
