"""
ZOE GBA 텍스트 번역 + 한글 ROM 인코딩
실행 방법: ANTHROPIC_API_KEY 환경변수 설정 후 실행
  $env:ANTHROPIC_API_KEY = "sk-ant-..."
  python translate_and_encode.py
"""
import sys, io, json, struct, os, re, time, urllib.request, urllib.error
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

ROM_PATH     = r"D:\Works\zoe\Zone of the Enders - The Fist of Mars (USA).gba"
OUT_ROM      = r"D:\Works\zoe\ZOE_Korean.gba"  # build_patch.py가 만든 파일
SYLL_IDX     = r"D:\Works\zoe\syllable_index.json"
TRANS_CACHE  = r"D:\Works\zoe\translation_cache.json"
TEXT_FILE    = r"D:\Works\zoe\extracted_text.txt"

API_KEY = os.environ.get('ANTHROPIC_API_KEY', '')

# ============================================================
# 텍스트 인코딩 규칙
# ============================================================
# 영문 원본: ROM 바이트 + 6 = ASCII
# 한글 인코딩:
#   음절 인덱스 i → byte1 = 0x80 + (i >> 8), byte2 = i & 0xFF
#   (i < 256이면 byte1 = 0x80, byte2 = i)
#   (i >= 256이면 byte1 = 0x81, byte2 = i-256 ... 등)
# 제어코드: 원본 유지 (0x00~0x1F)
# ASCII 문자: 원본 유지 (알파벳은 안 쓰지만 숫자/구두점은 유지)

with open(SYLL_IDX, encoding='utf-8') as f:
    _all_syll = json.load(f)
# Only indices 0-126 are supported (byte[1] = 0x80+idx, range 0x80-0xFE)
SYLL_TO_IDX = {k: v for k, v in _all_syll.items() if v < 127}

# ============================================================
# 한글 문자열 → ROM 바이트 인코딩
# ============================================================

def encode_korean(text):
    """
    한글 문자열을 ROM 바이트로 인코딩.
    한글 음절 → 1바이트: 0x80+syllable_idx  (idx 0-126 only)
      - 0x80-0xFE: 모두 printable(>0x0F), tile>0x20 → 직접 렌더 경로
      - 제어 코드 상호작용 없음 (0x01 마커 불필요)
    공백 → 0x20 (안전한 blank tile)
    줄바꿈 → 0x12 0x11 (원본 게임의 실제 줄바꿈 시퀀스)
    ASCII 구두점/숫자 → ROM 인코딩 (ASCII - 6)
    """
    result = bytearray()
    for ch in text:
        if '가' <= ch <= '힣':
            if ch not in SYLL_TO_IDX:
                continue  # 미지원 음절 건너뜀
            ch_idx = SYLL_TO_IDX[ch]
            result.append(0x80 + ch_idx)  # 단일 바이트
        elif ch == ' ':
            result.append(0x20)  # 공백 tile (safe)
        elif ch == '\n':
            # 원본 ROM 분석: 줄바꿈은 0x12 0x11 시퀀스
            # 0x12: jump table index 2, reads next byte (0x11) as param → newline
            result.append(0x12)
            result.append(0x11)
        elif ch.isascii() and 0x20 <= ord(ch) <= 0x7E:
            rom_byte = ord(ch) - 6
            if rom_byte >= 0x20:  # 안전한 범위
                result.append(rom_byte)
        # 나머지 문자는 무시
    return bytes(result)

def encode_korean_safe(text, max_bytes=None):
    """
    인코딩 후 크기 제한. max_bytes 초과 시 자름.
    단일 바이트 인코딩이므로 경계 처리 단순화.
    단, 줄바꿈(0x12 0x11)은 2바이트 단위로 자름.
    """
    encoded = encode_korean(text)
    if max_bytes and len(encoded) > max_bytes:
        truncated = bytearray()
        i = 0
        while i < len(encoded) and len(truncated) < max_bytes:
            b = encoded[i]
            if b == 0x12 and i + 1 < len(encoded) and encoded[i+1] == 0x11:
                # 줄바꿈 2바이트: 함께 들어가는 경우만 추가
                if len(truncated) + 2 <= max_bytes:
                    truncated.extend([0x12, 0x11])
                i += 2
            else:
                truncated.append(b)
                i += 1
        return bytes(truncated)
    return encoded

# ============================================================
# 텍스트 블록 파싱
# ============================================================

print("텍스트 파싱 중...")
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
        # 원본 raw 텍스트 저장, 정제된 키도 함께 저장
        cleaned = re.sub(r'[\x00-\x1F\x80-\xFF]', '', text)
        cleaned = re.sub(r'[^A-Za-z0-9 \.,!?\'-]', ' ', cleaned)
        cleaned = re.sub(r'\s+', ' ', cleaned).strip()
        blocks.append({'offset': offset, 'english': cleaned, 'raw': text})

blocks.sort(key=lambda x: x['offset'])
print(f"{len(blocks)}개 블록 파싱 완료")

# ============================================================
# 번역 캐시 로드
# ============================================================

cache = {}
if os.path.exists(TRANS_CACHE):
    with open(TRANS_CACHE, encoding='utf-8') as f:
        cache = json.load(f)
    print(f"캐시 로드: {len(cache)}개")

def save_cache():
    with open(TRANS_CACHE, 'w', encoding='utf-8') as f:
        json.dump(cache, f, ensure_ascii=False, indent=1)

# ============================================================
# Claude API 번역 함수
# ============================================================

def translate_batch(texts):
    """
    여러 텍스트를 한 번에 번역 (비용 절감)
    반환: {원문: 번역} dict
    """
    if not API_KEY:
        print("ERROR: ANTHROPIC_API_KEY 환경변수 없음!")
        return {}

    numbered = '\n'.join(f'[{i+1}] {t}' for i, t in enumerate(texts))
    prompt = f"""다음 GBA 게임 "Zone of the Enders: The Fist of Mars"의 영문 텍스트를 한국어로 번역해주세요.

규칙:
1. 게임 분위기(SF 전쟁물)에 맞는 자연스러운 한국어로 번역
2. 고유명사(Leo, Ares, Nadia, Warren 등 인물명/지명)는 음역 유지
3. 번호 형식 그대로 답변: [번호] 번역문
4. 짧은 UI 텍스트는 간결하게
5. 지원하는 음절만 사용 (완전한 한글 문장)

지원 음절 목록: {' '.join(list(SYLL_TO_IDX.keys())[:100])}...

번역할 텍스트:
{numbered}

답변 형식 (각 줄에 하나씩):
[1] 한국어 번역
[2] 한국어 번역
..."""

    payload = json.dumps({
        "model": "claude-haiku-4-5-20251001",
        "max_tokens": 4096,
        "messages": [{"role": "user", "content": prompt}]
    }).encode('utf-8')

    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=payload,
        headers={
            "x-api-key": API_KEY,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json"
        }
    )

    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            result = json.loads(resp.read())
        response_text = result['content'][0]['text']

        # 파싱: [1] 번역문 형식
        translations = {}
        for line in response_text.split('\n'):
            m = re.match(r'\[(\d+)\]\s*(.+)', line.strip())
            if m:
                idx = int(m.group(1)) - 1
                if 0 <= idx < len(texts):
                    translations[texts[idx]] = m.group(2).strip()
        return translations

    except urllib.error.HTTPError as e:
        print(f"API 오류: {e.code} {e.read().decode()[:200]}")
        return {}
    except Exception as e:
        print(f"오류: {e}")
        return {}

# ============================================================
# 번역 실행 (배치 처리)
# ============================================================

BATCH_SIZE = 20  # 한 번에 20개씩 번역
untranslated = [b for b in blocks if b['english'] not in cache]
print(f"\n번역 필요: {len(untranslated)}개 / 전체 {len(blocks)}개")

if not API_KEY:
    print("\n[API 키 없음] 수동 번역 테이블 사용")
    # 수동 번역 (주요 텍스트)
    MANUAL = {
        "MANKIND BEGAN TO LOOK BEYOND EARTH FOR SOLUTIONS AND BUILT THE FIRST SPACE TRACK ORBITAL ELEVATOR":
            "인류는 지구 너머에서 해결책을 찾기 시작했고 최초의 우주 궤도 엘리베이터를 건설했다",
        "EARTH S NATURAL RESOURCES HAD FINALLY BEEN EXHAUSTED AND THE TINY PLANET WAS UNABLE TO SUPPORT THE SOARING POPULATION OF HUMANS":
            "지구의 천연 자원이 마침내 고갈되었고 작은 행성은 급증하는 인구를 더 이상 부양할 수 없었다",
        "MORE THAN 2 MILLION PEOPLE TOOK UP RESIDENCES IN COLONIES ON THE MOON":
            "200만 명 이상의 사람들이 달의 콜로니에 거주하기 시작했다",
        "NEW CONFLICTS WERE JUST BEGINNING TO MATERIALIZE":
            "새로운 갈등이 막 표면 위로 드러나기 시작하고 있었다",
        "CHANGE COMMAND FOR ALL UNITS": "전 유닛 명령 변경",
        "MISSION COMPLETE": "임무 완료",
        "MISSION FAILED": "임무 실패",
        "ATTACK": "공격",
        "DEFEND": "방어",
        "RETREAT": "후퇴",
        "TARGET": "목표",
        "ENEMY": "적",
        "ALLY": "아군",
        "DAMAGE": "손상",
        "WARNING": "경고",
        "DANGER": "위험",
        "ESCAPE": "탈출",
        "LOADING": "로딩",
        "SAVE": "저장",
        "LOAD": "불러오기",
        "YES": "예",
        "NO": "아니오",
        "OK": "확인",
        "CANCEL": "취소",
        "SELECT": "선택",
        "START": "시작",
        "MENU": "메뉴",
        "STATUS": "상태",
        "HP": "HP",
        "ENERGY": "에너지",
        "WEAPON": "무기",
    }
    cache.update(MANUAL)
    save_cache()
    print(f"수동 번역 {len(MANUAL)}개 추가")
else:
    # API 번역 실행
    total_translated = 0
    for i in range(0, len(untranslated), BATCH_SIZE):
        batch = untranslated[i:i+BATCH_SIZE]
        texts = [b['english'] for b in batch]
        print(f"\n배치 번역 {i+1}-{min(i+BATCH_SIZE, len(untranslated))}/{len(untranslated)}...")

        translations = translate_batch(texts)
        cache.update(translations)
        total_translated += len(translations)

        if i % (BATCH_SIZE * 5) == 0:
            save_cache()
            print(f"  캐시 저장 ({len(cache)}개)")

        time.sleep(0.5)  # API 레이트 리밋

    save_cache()
    print(f"\n번역 완료: {total_translated}개 (캐시 총 {len(cache)}개)")

# ============================================================
# ROM에 번역 텍스트 삽입
# ============================================================

print("\n번역 텍스트 ROM 삽입 중...")

with open(OUT_ROM, 'rb') as f:
    rom = bytearray(f.read())

# 원본 텍스트 인코딩 함수 (영문 → ROM 바이트)
# 원본: ROM_byte + 6 = ASCII → ROM_byte = ASCII - 6
def encode_english_original(text):
    """원본 영문 인코딩 재현"""
    result = bytearray()
    for ch in text:
        if 0x20 <= ord(ch) <= 0x7E:
            result.append(ord(ch) - 6)
    return bytes(result)

replaced = 0
skipped_no_trans = 0
skipped_overflow = 0
skipped_bad_region = 0

# 유효한 ROM 텍스트 바이트 범위 (ROM_byte + 6 = ASCII 0x20-0x7E → ROM 0x1A-0x78)
# 제어코드: 0x00-0x0F (2바이트 시퀀스)
VALID_TEXT_BYTES = set(range(0x1A, 0x79)) | set(range(0x00, 0x10))

def is_valid_text_block(rom, offset, length):
    """offset에서 length 바이트가 실제 ROM 텍스트처럼 보이는지 검증."""
    if offset + length + 1 >= len(rom):
        return False
    # 최소 3글자 이상
    if length < 3:
        return False
    # 원본 ROM 바이트가 텍스트 범위 내여야 함
    valid = 0
    for i in range(min(length, 20)):  # 최대 20바이트만 검사
        b = rom[offset + i]
        if b in VALID_TEXT_BYTES:
            valid += 1
        elif b == 0x00:
            break  # null 종료자 = OK
        else:
            return False  # 범위 밖 바이트 = 텍스트 아님
    return valid >= 2

for block in blocks:
    offset = block['offset']
    english = block['english']
    korean = cache.get(english, '')

    if not korean:
        skipped_no_trans += 1
        continue

    orig_size = len(english)

    # 원본 ROM 바이트 검증 - 실제 텍스트 영역인지 확인
    if not is_valid_text_block(rom, offset, orig_size):
        skipped_bad_region += 1
        continue

    # 한글 인코딩
    kor_bytes = encode_korean_safe(korean, max_bytes=orig_size)

    if len(kor_bytes) == 0:
        skipped_bad_region += 1
        continue

    # ROM에 쓰기: 한글 bytes + null 종료자
    rom[offset:offset+len(kor_bytes)] = kor_bytes
    rom[offset+len(kor_bytes)] = 0x00  # null 종료자

    replaced += 1

print(f"삽입 완료: {replaced}개")
print(f"번역 없음: {skipped_no_trans}개")
print(f"비텍스트 영역 제외: {skipped_bad_region}개")
print(f"공간 부족: {skipped_overflow}개")

with open(OUT_ROM, 'wb') as f:
    f.write(rom)
print(f"\n최종 ROM: {OUT_ROM}")

# 통계
translated_ratio = (replaced / len(blocks) * 100) if blocks else 0
print(f"번역률: {replaced}/{len(blocks)} = {translated_ratio:.1f}%")

# ============================================================
# 지원 음절 커버리지 분석
# ============================================================

print("\n=== 음절 커버리지 분석 ===")
all_korean_in_cache = ''.join(v for v in cache.values() if v)
missing_syllables = set()
for ch in all_korean_in_cache:
    if '가' <= ch <= '힣' and ch not in SYLL_TO_IDX:
        missing_syllables.add(ch)

if missing_syllables:
    print(f"폰트 미지원 음절 {len(missing_syllables)}개: {''.join(sorted(missing_syllables))}")
    print("→ build_patch.py의 SYLLABLES_STR에 추가 필요")
else:
    print("모든 번역 음절이 폰트에 지원됨 ✓")
