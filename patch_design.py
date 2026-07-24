"""
ZOE GBA 한글 패치 - 인코딩 설계 및 코드 수정 계획

현재 인코딩:
  ROM 바이트 + 6 = ASCII 코드
  0x3B = 'A', 0x3C = 'B', ... 0x7E = 't'
  제어코드: 0x00(끝), 0x01, 0x1F 등

한글 인코딩 설계:
  0x80-0xBF: 한글 HIGH BYTE (64개)
  0x00-0xFF: 한글 LOW BYTE (256개)
  → 최대 16384개 음절 지원

  한글 음절 인덱스 = (high - 0x80) * 256 + low

  단, 첫 번째 바이트 0x80+ 감지 → 2바이트 한글 모드

ARM 코드 수정 포인트:
  0x03D98: 텍스트 렌더 메인 루프
  0x03DC8: 바이트 읽기 (현재 LDRB)
  0x03DDC: if byte ≤ 0x0F → 2-byte check

  수정 방향:
  1. 바이트 읽기 후 0x80 이상인지 체크
  2. 0x80 이상이면 → 한글 처리 루틴 호출
  3. 한글 처리: 다음 바이트 읽어서 음절 인덱스 계산
  4. 음절 인덱스로 ROM의 한글 폰트 테이블에서 타일 데이터 로드
  5. VRAM에 타일 복사 + 화면에 표시
"""

import struct

# GBA ROM 로드
with open(r"D:\Works\zoe\Zone of the Enders - The Fist of Mars (USA).gba", 'rb') as f:
    rom = bytearray(f.read())

print("=== 현재 텍스트 처리 코드 분석 ===")
print("""
0x03D98: 텍스트 처리 메인 루프 시작
0x03DC8: LDRB r0, [r4, #0]  ← 현재 텍스트 포인터에서 1바이트 읽기
0x03DCA: CMP r0, #0x00      ← 0이면 끝
0x03DDC: CMP r0, #0x0F      ← 0x0F 이하면 2바이트 제어코드
0x03DEA: SUB r0, #0x10      ← 제어코드 처리
0x03E50: BL 0x03900         ← 영문 글자 폭/렌더링

수정 포인트:
  0x03DC8 이후에 추가:
    LDRB r0, [r4, #0]
    CMP r0, #0x80          ← 새로 추가: 0x80 이상이면 한글
    BHS HANGUL_HANDLER     ← 한글 처리 루틴으로 점프
    (기존 코드 계속)
""")

# 패치 적용 위치 분석
print("=== 패치 가능한 ROM 공간 확인 ===")

# 현재 텍스트 영역: 0x076000-0x07C000 (6KB)
text_start = 0x076000
text_end = 0x07C000
text_size = text_end - text_start
print(f"텍스트 영역: 0x{text_start:06X}-0x{text_end:06X} = {text_size//1024}KB")

# ROM 끝 부분 빈 공간 확인
print("\nROM 후반부 빈 공간 탐색...")
rom_size = len(rom)
# 0xFF로 채워진 영역 찾기
empty_regions = []
i = 0
while i < rom_size - 1024:
    if rom[i] == 0xFF and all(b == 0xFF for b in rom[i:i+1024]):
        # 빈 영역 시작
        j = i
        while j < rom_size and rom[j] == 0xFF:
            j += 1
        if j - i > 0x8000:  # 32KB 이상 빈 공간
            empty_regions.append((i, j, j - i))
        i = j
    else:
        i += 1

for start, end, size in empty_regions:
    print(f"  빈 공간: 0x{start:06X}-0x{end:06X} = {size//1024}KB")

# 실제 ROM 사용 크기 확인
last_nonff = rom_size - 1
while last_nonff > 0 and rom[last_nonff] == 0xFF:
    last_nonff -= 1
print(f"\n실제 ROM 사용: 0x{last_nonff+1:06X} bytes = {(last_nonff+1)//1024}KB")
print(f"ROM 총 크기: {rom_size//1024}KB")
print(f"남은 공간: {(rom_size - last_nonff - 1)//1024}KB")

print("\n=== 한글 폰트 데이터 배치 계획 ===")
# 한글 폰트를 ROM 끝 빈 공간에 배치
if empty_regions:
    font_area_start = empty_regions[0][0]
    font_area_size = empty_regions[0][2]
    print(f"한글 폰트 배치 위치: ROM 0x{font_area_start:06X}")
    print(f"사용 가능 공간: {font_area_size//1024}KB")

    # 예상 폰트 크기
    # 2000개 음절 × 128 bytes/음절 = 256KB (raw)
    # LZ77 압축시 약 80-100KB
    print(f"\n폰트 데이터 예상 크기: 2000음절 × 128B = 256KB (압축 전)")
    print(f"LZ77 압축 후 예상: ~80KB")

print("\n=== ARM 패치 코드 설계 ===")
print("""
패치 코드 (Thumb ASM) - 한글 처리 루틴:

[기존 0x03DC8 코드 수정]
LDRB  r0, [r4]        ; 현재 바이트 읽기
CMP   r0, #0x80       ; 한글 마커?
BHS   HANGUL_PROC     ; 0x80+ 이면 한글 처리
; 기존 코드 계속...

[HANGUL_PROC] (새 루틴, ROM 빈 공간에 배치):
PUSH  {r1-r7, LR}
LDRB  r0, [r4]        ; 한글 HIGH BYTE (0x80-0xBF)
ADD   r4, #1          ; 포인터 전진
LDRB  r1, [r4]        ; 한글 LOW BYTE
ADD   r4, #1          ; 포인터 전진
SUB   r0, #0x80       ; high = byte1 - 0x80 (0-63)
LSL   r0, #8          ; high << 8
ORR   r0, r1          ; index = high * 256 + low
; r0 = 음절 인덱스

; 폰트 테이블에서 타일 데이터 주소 계산
LDR   r1, =HANGUL_FONT_ADDR  ; ROM 한글 폰트 기준 주소
LSL   r2, r0, #7      ; index * 128 (4 tiles × 32 bytes)
ADD   r1, r1, r2      ; 타일 데이터 주소

; VRAM 빈 타일 슬롯에 복사
; (기존 타일 할당자 사용)
; ...복잡한 타일 관리 코드...

POP   {r1-r7, PC}
""")
