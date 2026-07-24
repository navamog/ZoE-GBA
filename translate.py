"""
ZOE GBA 텍스트 번역 파이프라인
1. 텍스트 블록을 연속 장면으로 그룹화
2. 번역 결과를 저장
3. 한글 음절 사용 통계 추출
"""
import sys, io, re, json, struct
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

with open(r"D:\Works\zoe\extracted_text.txt", encoding='utf-8-sig') as f:
    content = f.read()

# 블록 파싱
raw_blocks = []
for b in content.split('\n[OFFSET:'):
    b = b.lstrip('[OFFSET:').strip()
    if not b:
        continue
    lines = b.split('\n')
    offset_str = lines[0].rstrip(']').strip()
    text = '\n'.join(lines[1:]).strip()
    try:
        offset = int(offset_str, 16)
    except:
        continue
    if text:
        raw_blocks.append((offset, text))

raw_blocks.sort(key=lambda x: x[0])
print(f"총 {len(raw_blocks)}개 텍스트 블록")

# 인접 블록 병합: 오프셋 차이가 작으면(< 0x200) 같은 장면
scenes = []
current_scene = []
prev_offset = -1

for offset, text in raw_blocks:
    if prev_offset < 0 or (offset - prev_offset) < 0x400:
        current_scene.append((offset, text))
    else:
        if current_scene:
            scenes.append(current_scene)
        current_scene = [(offset, text)]
    prev_offset = offset

if current_scene:
    scenes.append(current_scene)

print(f"총 {len(scenes)}개 장면으로 그룹화")

# 각 장면의 텍스트 재구성
def reconstruct_scene(scene):
    """블록들을 하나의 텍스트로 합치기"""
    texts = [t for _, t in scene]
    # 특수문자 제거 및 정리
    full = ' '.join(texts)
    # 제어문자 처리
    full = re.sub(r'[\x00-\x1F]+', ' ', full)
    full = re.sub(r'\s+', ' ', full).strip()
    return full

# 번역 데이터베이스 (이미 번역된 것)
translations = {}
try:
    with open(r"D:\Works\zoe\translations.json", encoding='utf-8') as f:
        translations = json.load(f)
    print(f"기존 번역 {len(translations)}개 로드")
except:
    print("새 번역 파일 생성")

# 장면별 번역 (수동 번역 테이블 - 주요 대화)
MANUAL_TRANSLATIONS = {
    # 프롤로그 내레이션
    "MANKIND BEGAN TO LOOK BEYOND EARTH FOR SOLUTIONS AND BUILT THE FIRST SPACE TRACK ORBITAL ELEVATOR":
        "인류는 지구 너머에서 해결책을 찾기 시작했고, 최초의 우주 궤도 엘리베이터를 건설했다.",

    "EARTH S NATURAL RESOURCES HAD FINALLY BEEN EXHAUSTED AND THE TINY PLANET WAS UNABLE TO SUPPORT THE SOARING POPULATION OF HUMANS":
        "지구의 천연 자원이 마침내 고갈되었고, 작은 행성은 급증하는 인구를 더 이상 부양할 수 없었다.",

    "AND COUNTRIES ALL OVER THE WORLD DOVE INTO COUNTLESS RESEARCH PROJECTS AND SPACE DEVELOPMENT PLANS":
        "세계 각국은 수많은 연구 프로젝트와 우주 개발 계획에 뛰어들었다.",

    "IT WAS THEN THAT THE HUMAN RACE CREATED AND DISCOVERED SEVERAL NEW TOOLS THAT WOULD CHANGE LIFE FOREVER":
        "그때 인류는 삶을 영원히 바꿀 여러 새로운 도구를 만들고 발견했다.",

    "MORE THAN 2 MILLION PEOPLE TOOK UP RESIDENCES IN COLONIES ON THE MOON":
        "200만 명 이상의 사람들이 달의 식민지에 거주하기 시작했다.",

    "NEW CONFLICTS WERE JUST BEGINNING TO MATERIALIZE":
        "새로운 갈등이 막 표면 위로 드러나기 시작하고 있었다.",

    "EARTH BEGAN TO REFER TO THESE COLONISTS AS":
        "지구인들은 이 식민지 주민들을",

    "A DEROGATORY TERM FOR THOSE EXPRESSING THEIR PREJUDICED ATTITUDES TOWARD NON":
        "지구 외 주민들을 향한 편견을 드러내는 비하 표현이었다.",

    # 시스템 메시지
    "CHANGE COMMAND FOR ALL UNITS": "전 유닛 명령 변경",
    "REPLENISHING AMMUNITION AND": "탄약 및 보급 중",
    "SPACE TRACK ORBITAL ELEVATOR": "우주 궤도 엘리베이터",
    "CONTROLLED INTERSPACE ROBOT": "공간 제어 로봇",
}

# 장면 분석 및 번역
print("\n=== 장면 분석 ===")
scene_data = []
for i, scene in enumerate(scenes[:50]):  # 처음 50개 장면
    offset = scene[0][0]
    text = reconstruct_scene(scene)

    # 번역 찾기
    translation = MANUAL_TRANSLATIONS.get(text, "")
    if not translation:
        # 부분 매칭 시도
        for eng, kor in MANUAL_TRANSLATIONS.items():
            if eng in text or text in eng:
                translation = kor
                break

    scene_data.append({
        'offset': offset,
        'blocks': [(o, t) for o, t in scene],
        'english': text,
        'korean': translation
    })

    if i < 20:
        print(f"\n장면 {i+1} [0x{offset:06X}]:")
        print(f"  영어: {text[:100]}")
        if translation:
            print(f"  한국어: {translation[:80]}")
        else:
            print(f"  (미번역)")

# 번역 저장
with open(r"D:\Works\zoe\scene_data.json", 'w', encoding='utf-8') as f:
    json.dump(scene_data, f, ensure_ascii=False, indent=2)

print(f"\n장면 데이터 저장: scene_data.json")
print(f"번역된 장면: {sum(1 for s in scene_data if s['korean'])}개")

# 한글 음절 통계 (번역된 텍스트에서)
all_korean = ''.join(s['korean'] for s in scene_data if s['korean'])
syllables_used = set()
for ch in all_korean:
    if '가' <= ch <= '힣':
        syllables_used.add(ch)

print(f"\n사용된 한글 음절: {len(syllables_used)}개")
print("음절 목록:", ''.join(sorted(syllables_used)[:50]))
