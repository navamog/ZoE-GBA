"""
GBA 한글 폰트 생성기
Windows GDI API (ctypes) 사용 - Pillow 불필요
한글 음절을 16x16 픽셀 4bpp GBA 타일 2x2로 변환
"""

import ctypes
import ctypes.wintypes as wintypes
import struct
import os

# Windows GDI 상수
SRCCOPY = 0x00CC0020
DIB_RGB_COLORS = 0
BI_RGB = 0
BLACK_BRUSH = 4

gdi32 = ctypes.windll.gdi32
user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [
        ("biSize", ctypes.c_uint32),
        ("biWidth", ctypes.c_int32),
        ("biHeight", ctypes.c_int32),
        ("biPlanes", ctypes.c_uint16),
        ("biBitCount", ctypes.c_uint16),
        ("biCompression", ctypes.c_uint32),
        ("biSizeImage", ctypes.c_uint32),
        ("biXPelsPerMeter", ctypes.c_int32),
        ("biYPelsPerMeter", ctypes.c_int32),
        ("biClrUsed", ctypes.c_uint32),
        ("biClrImportant", ctypes.c_uint32),
    ]

class BITMAPINFO(ctypes.Structure):
    _fields_ = [
        ("bmiHeader", BITMAPINFOHEADER),
        ("bmiColors", ctypes.c_uint32 * 256),
    ]

class LOGFONT(ctypes.Structure):
    _fields_ = [
        ("lfHeight", ctypes.c_int32),
        ("lfWidth", ctypes.c_int32),
        ("lfEscapement", ctypes.c_int32),
        ("lfOrientation", ctypes.c_int32),
        ("lfWeight", ctypes.c_int32),
        ("lfItalic", ctypes.c_uint8),
        ("lfUnderline", ctypes.c_uint8),
        ("lfStrikeOut", ctypes.c_uint8),
        ("lfCharSet", ctypes.c_uint8),
        ("lfOutPrecision", ctypes.c_uint8),
        ("lfClipPrecision", ctypes.c_uint8),
        ("lfQuality", ctypes.c_uint8),
        ("lfPitchAndFamily", ctypes.c_uint8),
        ("lfFaceName", ctypes.c_wchar * 32),
    ]

def render_char_16x16(char, font_name="Gulim", font_size=13):
    """문자를 16x16 픽셀 1bpp로 렌더링, numpy 없이 순수 픽셀 리스트 반환"""
    W, H = 16, 16

    # DC 생성
    screen_dc = user32.GetDC(None)
    mem_dc = gdi32.CreateCompatibleDC(screen_dc)

    # DIB 섹션 생성 (1bpp grayscale → 32bpp로 실제 렌더링)
    bmi = BITMAPINFO()
    bmi.bmiHeader.biSize = ctypes.sizeof(BITMAPINFOHEADER)
    bmi.bmiHeader.biWidth = W
    bmi.bmiHeader.biHeight = -H  # top-down
    bmi.bmiHeader.biPlanes = 1
    bmi.bmiHeader.biBitCount = 32
    bmi.bmiHeader.biCompression = BI_RGB

    bits_ptr = ctypes.c_void_p()
    hbm = gdi32.CreateDIBSection(mem_dc, ctypes.byref(bmi), DIB_RGB_COLORS,
                                   ctypes.byref(bits_ptr), None, 0)
    old_bm = gdi32.SelectObject(mem_dc, hbm)

    # 배경을 검정으로
    gdi32.PatBlt(mem_dc, 0, 0, W, H, 0x000042)  # BLACKNESS

    # 폰트 생성
    lf = LOGFONT()
    lf.lfHeight = -font_size
    lf.lfWeight = 400  # FW_NORMAL
    lf.lfCharSet = 129  # HANGEUL_CHARSET
    lf.lfQuality = 1  # DRAFT_QUALITY (안티앨리어싱 없음)
    lf.lfFaceName = font_name

    hfont = gdi32.CreateFontIndirectW(ctypes.byref(lf))
    old_font = gdi32.SelectObject(mem_dc, hfont)

    # 흰 글자, 검은 배경
    gdi32.SetTextColor(mem_dc, 0x00FFFFFF)
    gdi32.SetBkMode(mem_dc, 1)  # TRANSPARENT
    gdi32.SetBkColor(mem_dc, 0x00000000)

    # 문자 크기 확인 후 중앙 배치
    size = ctypes.wintypes.SIZE()
    gdi32.GetTextExtentPoint32W(mem_dc, char, 1, ctypes.byref(size))
    x = max(0, (W - size.cx) // 2)
    y = max(0, (H - size.cy) // 2)

    gdi32.TextOutW(mem_dc, x, y, char, 1)

    # 픽셀 읽기
    pixels = (ctypes.c_uint32 * (W * H))()
    ctypes.memmove(pixels, bits_ptr, W * H * 4)

    # 픽셀 → 1/0 배열
    bitmap = []
    for row in range(H):
        row_data = []
        for col in range(W):
            p = pixels[row * W + col]
            r = (p >> 16) & 0xFF
            g = (p >> 8) & 0xFF
            b = p & 0xFF
            luma = (r + g + b) // 3
            row_data.append(1 if luma > 64 else 0)
        bitmap.append(row_data)

    # 정리
    gdi32.SelectObject(mem_dc, old_font)
    gdi32.SelectObject(mem_dc, old_bm)
    gdi32.DeleteObject(hfont)
    gdi32.DeleteObject(hbm)
    gdi32.DeleteDC(mem_dc)
    user32.ReleaseDC(None, screen_dc)

    return bitmap

def bitmap_to_gba_tiles_4bpp(bitmap_16x16, fg_color=9, bg_color=0):
    """
    16x16 픽셀 비트맵 → GBA 4bpp 타일 4개 (2x2 배열)
    반환: bytes (4 tiles × 32 bytes = 128 bytes)
    타일 배열: [TL, TR, BL, BR] (각 8x8)
    """
    H, W = 16, 16
    assert len(bitmap_16x16) == H and len(bitmap_16x16[0]) == W

    # 4 타일: top-left, top-right, bottom-left, bottom-right
    tile_data = [bytearray(32) for _ in range(4)]

    for row in range(16):
        for col in range(16):
            pixel = fg_color if bitmap_16x16[row][col] else bg_color

            # 어느 타일인지
            tile_col = col // 8   # 0=left, 1=right
            tile_row = row // 8   # 0=top, 1=bottom
            tile_idx = tile_row * 2 + tile_col  # 0=TL,1=TR,2=BL,3=BR

            # 타일 내 위치
            local_col = col % 8
            local_row = row % 8

            # 4bpp: 각 바이트에 2픽셀 (low nibble = even col, high nibble = odd col)
            byte_idx = local_row * 4 + local_col // 2
            if local_col % 2 == 0:
                tile_data[tile_idx][byte_idx] = (tile_data[tile_idx][byte_idx] & 0xF0) | (pixel & 0xF)
            else:
                tile_data[tile_idx][byte_idx] = (tile_data[tile_idx][byte_idx] & 0x0F) | ((pixel & 0xF) << 4)

    return b''.join(tile_data)

def lz77_compress(data):
    """GBA LZ77 압축 (type 0x10)"""
    out = bytearray()
    out += struct.pack('<I', 0x10 | (len(data) << 8))

    i = 0
    while i < len(data):
        # 8개 청크 처리
        flags_pos = len(out)
        out.append(0)
        flags = 0

        for bit in range(8):
            if i >= len(data):
                break

            # 최장 매칭 찾기 (최대 18바이트, 최대 4096바이트 이전)
            best_len = 2  # minimum match = 3
            best_disp = 0

            start = max(0, i - 4096)
            for j in range(start, i):
                length = 0
                while length < 18 and (i + length) < len(data) and data[j + length] == data[i + length]:
                    length += 1
                if length > best_len:
                    best_len = length
                    best_disp = i - j - 1

            if best_len >= 3:
                flags |= (0x80 >> bit)
                out.append(((best_len - 3) << 4) | (best_disp >> 8))
                out.append(best_disp & 0xFF)
                i += best_len
            else:
                out.append(data[i])
                i += 1

        out[flags_pos] = flags

    # 4바이트 정렬
    while len(out) % 4 != 0:
        out.append(0)

    return bytes(out)

# 자주 쓰이는 한글 음절 (빈도순)
# 한국어 텍스트에서 가장 자주 나오는 음절들
COMMON_SYLLABLES = [
    # 빈도 높은 한글 음절들
    '이','다','에','의','는','가','을','로','한','하','고','기','어','서','지','인',
    '을','들','도','라','대','사','그','으','시','으','아','자','수','보','리','화',
    '만','것','부','국','나','게','생','우','공','을','에','으','현','년','이','세',
    '전','미','중','상','정','문','동','일','명','물','학','방','실','무','표','위',
    '금','면','원','용','여','야','계','조','데','합','선','요','경','개','성','오',
    '천','남','군','시','때','내','바','소','을','활','신','회','민','기','주','마',
    '제','장','노','업','인','마','산','모','스','합','분','구','간','파','안','복',
    '진','관','어','까','력','차','개','팀','들','같','좋','없','있','못','됩','니',
    '다','까','요','죠','군','죠','겠','줄','알','봐','좀','더','그','런','데','뭐',
    '나','아','네','오','예','응','음','흠','흐','허','하','어','이','우','와','야',
    # ZOE 게임 특유 단어들
    '전','쟁','지','구','인','류','우','주','로','봇','병','기','승','무','원',
    '적','공','격','방','어','임','무','완','료','목','표','파','괴','작','전',
    '레','오','에','렌','켄','가','이','나','비','바','하','자','이','데','온',
    '콕','핏','마','스','터','서','브','파','일','럿','콜','로','니','살','해',
    '넥','타','리','스','이','카','루','스','칼','리','브','알','시','오','님',
]

# 중복 제거, 순서 유지
seen = set()
SYLLABLES = []
for s in COMMON_SYLLABLES:
    if s not in seen:
        seen.add(s)
        SYLLABLES.append(s)

print(f"총 {len(SYLLABLES)}개 한글 음절 생성 예정")

# 폰트 생성
font_tiles = {}
failed = []

print("렌더링 중...")
for i, char in enumerate(SYLLABLES):
    try:
        bitmap = render_char_16x16(char, font_name="Gulim", font_size=13)
        tiles = bitmap_to_gba_tiles_4bpp(bitmap, fg_color=9, bg_color=0)
        font_tiles[char] = tiles
        if i % 50 == 0:
            print(f"  {i}/{len(SYLLABLES)}: {char}")
    except Exception as e:
        failed.append((char, str(e)))
        print(f"  FAIL: {char} - {e}")

print(f"\n완료: {len(font_tiles)}개 성공, {len(failed)}개 실패")

# 결과 저장
# 포맷: [음절 수(2B)] [음절1(UTF-8 3B)] [tile_offset(4B)] ... [tile data]
out_path = r"D:\Works\zoe\korean_font.bin"
with open(out_path, 'wb') as f:
    chars = list(font_tiles.keys())
    n = len(chars)

    # 헤더: magic + count
    f.write(b'KFNT')
    f.write(struct.pack('<H', n))

    # 인덱스 테이블: [utf-8 음절(3B)] [offset(4B)]
    # 각 항목: 7 bytes
    tile_data_start = 6 + n * 7

    for i, char in enumerate(chars):
        utf8 = char.encode('utf-8')
        assert len(utf8) == 3, f"Expected 3-byte UTF-8 for '{char}'"
        offset = tile_data_start + i * 128
        f.write(utf8)
        f.write(struct.pack('<I', offset))

    # 타일 데이터: 128 bytes per char (4 tiles × 32 bytes)
    for char in chars:
        f.write(font_tiles[char])

file_size = os.path.getsize(out_path)
print(f"\n저장: {out_path}")
print(f"파일 크기: {file_size} bytes ({file_size//1024}KB)")
print(f"  헤더: 6 bytes")
print(f"  인덱스: {n*7} bytes")
print(f"  타일 데이터: {n*128} bytes")

# 샘플 확인: '이' 문자 ASCII 아트
if '이' in font_tiles:
    tile_data = font_tiles['이']
    print("\n'이' 문자 미리보기 (16x16):")
    # 16x16 재구성
    for row in range(16):
        line = ''
        for col in range(16):
            tile_col = col // 8
            tile_row = row // 8
            tile_idx = tile_row * 2 + tile_col
            local_col = col % 8
            local_row = row % 8
            byte_idx = local_row * 4 + local_col // 2
            b = tile_data[tile_idx * 32 + byte_idx]
            px = (b >> 4) if local_col % 2 else (b & 0xF)
            line += '#' if px > 0 else '.'
        print(f"  {line}")
