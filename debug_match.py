import sys, io, json, re
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

with open(r'D:\Works\zoe\translation_cache.json', encoding='utf-8') as f:
    cache = json.load(f)

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
        cleaned = re.sub(r'[\x00-\x1F\x80-\xFF]', '', text)
        cleaned = re.sub(r'[^A-Za-z0-9 \.,!?\'-]', ' ', cleaned)
        cleaned = re.sub(r'\s+', ' ', cleaned).strip()
        blocks.append({'offset': offset, 'english': cleaned})

# Show first 20 blocks and whether they hit cache
print("=== 처음 20개 블록 캐시 매칭 ===")
for b in blocks[:20]:
    hit = b['english'] in cache
    print(f"  {'✓' if hit else '✗'} [{b['offset']:06X}] '{b['english'][:60]}'")

# Show how many total cache hits
hits = sum(1 for b in blocks if b['english'] in cache)
print(f"\n총 캐시 매칭: {hits}/{len(blocks)}")

# Show first 10 fragments cache keys
print("\n=== 캐시 샘플 키 ===")
for k in list(cache.keys())[:20]:
    print(f"  '{k[:60]}'")
