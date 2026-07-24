import sys, io, re, json
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
    t = re.sub(r'[\x00-\x1F\x80-\xFF]', '', t)
    t = re.sub(r'[^A-Za-z0-9 \.,!?\'-]', ' ', t)
    t = re.sub(r'\s+', ' ', t).strip()
    return t

# 번역할 텍스트만 (알파벳 6자 이상)
out = []
for offset, raw in blocks:
    c = clean(raw)
    if len(re.sub(r'[^A-Za-z]','',c)) >= 6:
        out.append({'offset': f'0x{offset:06X}', 'text': c})

# 고유한 텍스트 추출 (오프셋은 첫번째 것)
seen = {}
unique_out = []
for item in out:
    if item['text'] not in seen:
        seen[item['text']] = item['offset']
        unique_out.append(item)

with open(r'D:\Works\zoe\texts_to_translate.json', 'w', encoding='utf-8') as f:
    json.dump(unique_out, f, ensure_ascii=False, indent=1)

print(f'저장: {len(unique_out)}개 고유 텍스트 -> texts_to_translate.json')

# 카테고리별 분류
ui_keywords = ['COMMAND','UNIT','ATTACK','DEFEND','RETREAT','CANCEL','SELECT',
               'STATUS','SAVE','LOAD','MENU','OPTIONS','MISSION','PHASE','STAGE',
               'COMPLETE','FAILED','VICTORY','DAMAGE','HP','MP','EXP','LEVEL',
               'WEAPON','SUPPLY','REPAIR','MOVE','WAIT','END TURN']
story_texts = [t for t in unique_out if not any(k in t['text'].upper() for k in ui_keywords)]
ui_texts = [t for t in unique_out if any(k in t['text'].upper() for k in ui_keywords)]
print(f'UI/메뉴: {len(ui_texts)}개, 스토리: {len(story_texts)}개')
