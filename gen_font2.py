"""
GBA 한글 폰트 생성기 v2
- Galmuri11.bdf 직접 파싱 (렌더링 엔진 불필요, Windows GDI 불필요)
- BDF 11x11 비트맵 → 16x16 1bpp GBA 글리프 (32 bytes/char)
- build_patch.py의 GLYPH_ROM_OFF에 바로 삽입 가능한 포맷
"""

import struct, json, os, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

BDF_PATH   = r"D:\Works\zoe\galmuri_extracted\Galmuri11.bdf"
SYLL_PATH  = r"D:\Works\zoe\syllable_index.json"
OUT_PATH   = r"D:\Works\zoe\korean_glyphs2.bin"

# ============================================================
# 1. BDF 파서
# ============================================================

def parse_bdf(path):
    """BDF 파일에서 {codepoint: [[0/1 row], ...]} 딕셔너리 반환"""
    glyphs = {}
    with open(path, encoding='utf-8') as f:
        lines = f.readlines()

    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if line.startswith('STARTCHAR'):
            encoding = None
            bbx_w = bbx_h = bbx_x = bbx_y = 0
            bitmap_rows = []
            in_bitmap = False
            i += 1
            while i < len(lines):
                l = lines[i].strip()
                if l.startswith('ENCODING'):
                    encoding = int(l.split()[1])
                elif l.startswith('BBX'):
                    parts = l.split()
                    bbx_w, bbx_h, bbx_x, bbx_y = int(parts[1]), int(parts[2]), int(parts[3]), int(parts[4])
                elif l == 'BITMAP':
                    in_bitmap = True
                elif l == 'ENDCHAR':
                    break
                elif in_bitmap:
                    bitmap_rows.append(l)
                i += 1
            # 비트맵 행 파싱
            if encoding is not None and bitmap_rows:
                rows = []
                row_bytes = (bbx_w + 7) // 8  # BDF는 바이트 경계
                hex_bytes = (row_bytes + 1) & ~1  # BDF는 짝수 바이트
                for hex_str in bitmap_rows:
                    val = int(hex_str, 16)
                    # val의 비트 수 = hex_bytes * 8, MSB first
                    total_bits = hex_bytes * 8
                    row = []
                    for bit in range(bbx_w):
                        # 비트 위치: MSB = bit 0
                        shift = total_bits - 1 - bit
                        row.append(1 if (val >> shift) & 1 else 0)
                    rows.append(row)
                glyphs[encoding] = {
                    'rows': rows,
                    'bbx_w': bbx_w,
                    'bbx_h': bbx_h,
                    'bbx_x': bbx_x,
                    'bbx_y': bbx_y,
                }
        i += 1
    return glyphs

print("BDF 파싱 중...", flush=True)
bdf = parse_bdf(BDF_PATH)
korean_range = {cp: g for cp, g in bdf.items() if 0xAC00 <= cp <= 0xD7A3}
print(f"  BDF 총 글리프: {len(bdf):,}개")
print(f"  한글 음절: {len(korean_range):,}개")

# ============================================================
# 2. BDF 글리프 → 16x16 1bpp GBA 포맷
# ============================================================
# GBA 1bpp: 32 bytes (16행 × 2바이트)
# 비트 순서: 각 행 바이트0 bit7=col0, bit6=col1 ... 바이트1 bit7=col8 ... bit0=col15
# Galmuri11 BBX: 11×11, x_off=0, y_off=0 → 16×16 캔버스에 배치
# 배치: x=0 (왼쪽 정렬), y=2 (약간 위에서 시작, 아래 패딩)

CANVAS_W = 16
CANVAS_H = 16
X_OFFSET = 1   # 왼쪽에서 1px 여백
Y_OFFSET = 2   # 위에서 2px 내려서 배치 (11px 글리프 → 2+11+3 = 16)

def glyph_to_1bpp_16x16(g_info):
    """BDF 글리프 정보 → 32바이트 1bpp GBA 글리프"""
    canvas = [[0] * CANVAS_W for _ in range(CANVAS_H)]
    rows = g_info['rows']
    bbx_w = g_info['bbx_w']
    bbx_h = g_info['bbx_h']

    for r, row in enumerate(rows):
        canvas_y = Y_OFFSET + r
        if canvas_y >= CANVAS_H:
            break
        for c, px in enumerate(row):
            canvas_x = X_OFFSET + c
            if canvas_x >= CANVAS_W:
                break
            canvas[canvas_y][canvas_x] = px

    # 16×16 → 32 bytes (1bpp, MSB first)
    data = bytearray(32)
    for r in range(CANVAS_H):
        for c in range(CANVAS_W):
            if canvas[r][c]:
                if c < 8:
                    data[r * 2 + 0] |= (1 << (7 - c))
                else:
                    data[r * 2 + 1] |= (1 << (15 - c))
    return bytes(data)

# ============================================================
# 3. syllable_index.json 순서대로 글리프 데이터 생성
# ============================================================
with open(SYLL_PATH, encoding='utf-8') as f:
    syll_dict = json.load(f)

MAX_SYLLABLES = 127
syllables = [ch for ch, _ in sorted(syll_dict.items(), key=lambda x: x[1])[:MAX_SYLLABLES]]
print(f"\n음절 {len(syllables)}개: {syllables[:8]}...")

glyph_data = bytearray()
missing = []
previews = []

for i, syl in enumerate(syllables):
    cp = ord(syl)
    if cp in bdf:
        data = glyph_to_1bpp_16x16(bdf[cp])
    else:
        data = bytes(32)  # 빈 글리프 (폰트에 없는 경우)
        missing.append(syl)
    glyph_data += data
    if i < 5:
        previews.append((syl, data))

assert len(glyph_data) == MAX_SYLLABLES * 32, f"크기 오류: {len(glyph_data)}"

# ============================================================
# 4. 저장
# ============================================================
with open(OUT_PATH, 'wb') as f:
    f.write(glyph_data)

print(f"\n저장: {OUT_PATH}")
print(f"  크기: {len(glyph_data)} bytes ({MAX_SYLLABLES} 글리프 × 32 bytes)")
if missing:
    print(f"  경고: BDF에 없는 음절 {len(missing)}개: {missing}")

# ============================================================
# 5. 미리보기 (ASCII 아트)
# ============================================================
def preview_glyph(data, label):
    print(f"\n  [{label}]")
    for r in range(16):
        row = ""
        for c in range(16):
            if c < 8:
                px = (data[r*2+0] >> (7-c)) & 1
            else:
                px = (data[r*2+1] >> (15-c)) & 1
            row += "█" if px else "·"
        print(f"  {row}")

print("\n=== 미리보기 ===")
for syl, data in previews:
    preview_glyph(data, syl)

print(f"\n완료! build_patch.py에서 GLYPH_ROM_OFF에 korean_glyphs2.bin 사용 가능")
