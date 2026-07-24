import sys, io, re
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

with open(r'D:\Works\zoe\extracted_text.txt', encoding='utf-8-sig') as f:
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
        blocks.append((offset, text))

blocks.sort(key=lambda x: x[0])

def clean(t):
    t = re.sub(r'[\x00-\x1F\x80-\xFF]', ' ', t)
    t = re.sub(r'[\^\\`]', ' ', t)
    t = re.sub(r'\s+', ' ', t).strip()
    return t

meaningful = [(o, clean(t)) for o, t in blocks if len(re.sub(r'[^A-Za-z]','',t)) >= 8]
print(f'의미있는 블록: {len(meaningful)}개 / 전체 {len(blocks)}개')

uniq = list(dict.fromkeys(t for _,t in meaningful))
print(f'고유 텍스트: {len(uniq)}개')

translatable = [t for t in uniq if 5 <= len(t) <= 200]
print(f'번역 대상: {len(translatable)}개')
print()
print('처음 50개:')
for i, t in enumerate(translatable[:50]):
    print(f'[{i+1:3d}] {t}')
