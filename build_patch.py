"""
ZOE GBA 한글 패치 빌더 (v4)
핵심 수정: 038AC는 IWRAM 슬롯 주소를 반환해야 함
- 한글 경로: ROM 글리프 → IWRAM 슬롯 복사 후 IWRAM 주소 반환
- 영어 경로: 원본 038B4로 점프 (기존과 동일)
"""
import ctypes, ctypes.wintypes, struct, os, sys, io, json
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

ROM_PATH = r"D:\Works\zoe\Zone of the Enders - The Fist of Mars (USA).gba"
OUT_ROM  = r"D:\Works\zoe\ZOE_Korean.gba"

TRAMPOLINE_ROM_OFF = 0x78C540
GLYPH_ROM_OFF      = 0x78C590   # 트램폴린 76바이트 + 패딩 후
TRAMPOLINE_GBA     = 0x08000000 + TRAMPOLINE_ROM_OFF
GLYPH_GBA          = 0x08000000 + GLYPH_ROM_OFF

HOOK_ROM_OFF       = 0x038AC
MAX_SYLLABLES      = 127
ENGLISH_RESUME_GBA = 0x080038B5
IWRAM_BASE         = 0x03003320   # 원본 038AC pool에서 확인된 IWRAM 글리프 슬롯 베이스

# ============================================================
# 1. GDI 글리프 렌더링
# ============================================================
gdi32  = ctypes.windll.gdi32
user32 = ctypes.windll.user32

class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [("biSize",ctypes.c_uint32),("biWidth",ctypes.c_int32),
                ("biHeight",ctypes.c_int32),("biPlanes",ctypes.c_uint16),
                ("biBitCount",ctypes.c_uint16),("biCompression",ctypes.c_uint32),
                ("biSizeImage",ctypes.c_uint32),("biXPelsPerMeter",ctypes.c_int32),
                ("biYPelsPerMeter",ctypes.c_int32),("biClrUsed",ctypes.c_uint32),
                ("biClrImportant",ctypes.c_uint32)]

def render_16x16(char):
    W, H = 16, 16
    hdc = user32.GetDC(None)
    mem_dc = gdi32.CreateCompatibleDC(hdc)
    bih = BITMAPINFOHEADER()
    bih.biSize = ctypes.sizeof(BITMAPINFOHEADER)
    bih.biWidth = W; bih.biHeight = -H
    bih.biPlanes = 1; bih.biBitCount = 32; bih.biCompression = 0
    class BITMAPINFO(ctypes.Structure):
        _fields_ = [("bmiHeader", BITMAPINFOHEADER), ("bmiColors", ctypes.c_uint32 * 3)]
    bmi = BITMAPINFO(); bmi.bmiHeader = bih
    pbits = ctypes.c_void_p()
    hbmp = gdi32.CreateDIBSection(mem_dc, ctypes.byref(bmi), 0, ctypes.byref(pbits), None, 0)
    gdi32.SelectObject(mem_dc, hbmp)
    hbr = gdi32.CreateSolidBrush(0x00FFFFFF)
    rect = ctypes.wintypes.RECT(0, 0, W, H)
    user32.FillRect(mem_dc, ctypes.byref(rect), hbr)
    gdi32.DeleteObject(hbr)
    hfont = gdi32.CreateFontW(14, 0, 0, 0, 400, 0, 0, 0, 129, 0, 0, 0, 0, "Gulim")
    gdi32.SelectObject(mem_dc, hfont)
    gdi32.SetTextColor(mem_dc, 0x00000000)
    gdi32.SetBkMode(mem_dc, 1)
    buf = ctypes.create_unicode_buffer(char)
    gdi32.TextOutW(mem_dc, 0, 0, buf, 1)
    pixels = (ctypes.c_uint32 * (W * H))()
    ctypes.memmove(pixels, pbits, W * H * 4)
    grid = []
    for r in range(H):
        row = [1 if (pixels[r*W+c] & 0xFFFFFF) == 0 else 0 for c in range(W)]
        grid.append(row)
    gdi32.DeleteObject(hfont); gdi32.DeleteObject(hbmp)
    gdi32.DeleteDC(mem_dc); user32.ReleaseDC(None, hdc)
    return grid

def to_1bpp(grid):
    data = bytearray(32)
    # Only 15 rows — bytes 30-31 stay 0x00 (renderer reads them as metadata)
    for r in range(15):
        for c in range(16):
            if grid[r][c]:
                if c < 8: data[r*2+0] |= (1 << (7-c))
                else:     data[r*2+1] |= (1 << (15-c))
    return bytes(data)

# ============================================================
# 2. 음절 로드
# ============================================================
with open(r"D:\Works\zoe\syllable_index.json", encoding="utf-8") as f:
    syll_dict = json.load(f)
syllables = [ch for ch, _ in sorted(syll_dict.items(), key=lambda x: x[1])[:MAX_SYLLABLES]]
print(f"음절 {len(syllables)}개: {syllables[:10]}...")

# ============================================================
# 3. 글리프 생성
# ============================================================
glyph_data = bytearray()
for i, syl in enumerate(syllables):
    data = to_1bpp(render_16x16(syl))
    glyph_data += data
    if i < 3:
        print(f"  syl[{i}]='{syl}': {data[0]:02X} {data[1]:02X}")
assert len(glyph_data) == MAX_SYLLABLES * 32
print(f"글리프 데이터: {len(glyph_data)} bytes @ ROM 0x{GLYPH_ROM_OFF:06X}")

# ============================================================
# 4. 트램폴린 (76 bytes at 0x78C540)
# ============================================================
#
# Entry: r0=slot, r1=tile
#
# 핵심 발견: 038AC 원본은 IWRAM 슬롯(0x03003320+slot*32)에 글리프 복사 후
# IWRAM 주소를 반환함. 우리도 동일하게 해야 함.
#
# 한글 경로 (tile 0x80-0xFE):
#   1. IWRAM dest = IWRAM_BASE + slot*32
#   2. ROM src    = GLYPH_GBA + (tile-0x80)*32
#   3. LDMIA/STMIA로 32바이트 복사
#   4. r0 = IWRAM dest 반환
#
# Layout (all offsets from 0x78C540):
# +00: 0A 1C  MOV r2, r1
# +02: 80 3A  SUB r2, #0x80
# +04: 7E 2A  CMP r2, #0x7E
# +06: 17 D8  BHI → +38 (english_path)
# +08: 30 B5  PUSH {r4,r5,lr}
# +0A: 03 1C  MOV r3, r0         ; r3 = slot
# +0C: 5B 01  LSL r3, r3, #5    ; r3 = slot*32
# +0E: 08 48  LDR r0, [PC,#32]  ; r0 = IWRAM_BASE  (pool1@+30)
# +10: 1B 18  ADD r3, r3, r0    ; r3 = IWRAM_BASE + slot*32 = dest
# +12: 08 B4  PUSH {r3}         ; save dest for return
# +14: 52 01  LSL r2, r2, #5    ; r2 = idx*32
# +16: 07 48  LDR r0, [PC,#28]  ; r0 = GLYPH_GBA   (pool2@+34)
# +18: 12 18  ADD r2, r2, r0    ; r2 = GLYPH_GBA + idx*32 = src
# +1A: 30 CA  LDMIA r2!, {r4,r5}
# +1C: 30 C3  STMIA r3!, {r4,r5}
# +1E: 30 CA  LDMIA r2!, {r4,r5}
# +20: 30 C3  STMIA r3!, {r4,r5}
# +22: 30 CA  LDMIA r2!, {r4,r5}
# +24: 30 C3  STMIA r3!, {r4,r5}
# +26: 30 CA  LDMIA r2!, {r4,r5}
# +28: 30 C3  STMIA r3!, {r4,r5}
# +2A: 01 BC  POP {r0}          ; r0 = IWRAM dest
# +2C: 30 BD  POP {r4,r5,pc}   ; return
# +2E: 00 00  padding
# +30: [IWRAM_BASE = 0x03003320]  pool1
# +34: [GLYPH_GBA]               pool2
# +38: 30 B5  PUSH {r4,r5,lr}   english_path
# +3A: 04 1C  MOV r4, r0
# +3C: 24 06  LSL r4, r4, #24
# +3E: 09 04  LSL r1, r1, #16
# +40: 01 48  LDR r0, [PC,#4]   pool3@+48
# +42: 00 47  BX r0
# +44: 00 00  padding
# +46: 00 00  padding
# +48: [ENGLISH_RESUME_GBA]      pool3
# +4C: (end, total 76 bytes)
#
# PC-relative LDR 검증:
#   +0E (0x78C54E): PC_aligned=0x78C550, pool1@0x78C570=+30 → offset=(0x570-0x550)/4=8 ✓
#   +16 (0x78C556): PC_aligned=0x78C558, pool2@0x78C574=+34 → offset=(0x574-0x558)/4=7 ✓
#   +40 (0x78C580): PC_aligned=0x78C584, pool3@0x78C588=+48 → offset=(0x588-0x584)/4=1 ✓
#   BHI offset: (+38-(+06+4))/2 = (0x38-0x0A)/2 = 0x17 = 23 ✓

def u32le(v):
    return [(v>>0)&0xFF, (v>>8)&0xFF, (v>>16)&0xFF, (v>>24)&0xFF]

trampoline = bytearray([
    # Korean check
    0x0A, 0x1C,  # +00: MOV r2, r1
    0x80, 0x3A,  # +02: SUB r2, #0x80
    0x7E, 0x2A,  # +04: CMP r2, #0x7E
    0x17, 0xD8,  # +06: BHI → +38 (english)
    # Korean path
    0x30, 0xB5,  # +08: PUSH {r4,r5,lr}
    0x03, 0x1C,  # +0A: MOV r3, r0
    0x5B, 0x01,  # +0C: LSL r3, r3, #5
    0x08, 0x48,  # +0E: LDR r0, [PC, #32]  → pool1@+30
    0x1B, 0x18,  # +10: ADD r3, r3, r0
    0x08, 0xB4,  # +12: PUSH {r3}
    0x52, 0x01,  # +14: LSL r2, r2, #5
    0x07, 0x48,  # +16: LDR r0, [PC, #28]  → pool2@+34
    0x12, 0x18,  # +18: ADD r2, r2, r0
    0x30, 0xCA,  # +1A: LDMIA r2!, {r4,r5}
    0x30, 0xC3,  # +1C: STMIA r3!, {r4,r5}
    0x30, 0xCA,  # +1E: LDMIA r2!, {r4,r5}
    0x30, 0xC3,  # +20: STMIA r3!, {r4,r5}
    0x30, 0xCA,  # +22: LDMIA r2!, {r4,r5}
    0x30, 0xC3,  # +24: STMIA r3!, {r4,r5}
    0x30, 0xCA,  # +26: LDMIA r2!, {r4,r5}
    0x30, 0xC3,  # +28: STMIA r3!, {r4,r5}
    0x01, 0xBC,  # +2A: POP {r0}
    0x30, 0xBD,  # +2C: POP {r4,r5,pc}
    0x00, 0x00,  # +2E: padding
    # pool1 @ +30
    *u32le(IWRAM_BASE),
    # pool2 @ +34
    *u32le(GLYPH_GBA),
    # english_path @ +38
    0x30, 0xB5,  # +38: PUSH {r4,r5,lr}
    0x04, 0x1C,  # +3A: MOV r4, r0
    0x24, 0x06,  # +3C: LSL r4, r4, #24
    0x09, 0x04,  # +3E: LSL r1, r1, #16
    0x01, 0x48,  # +40: LDR r0, [PC, #4]   → pool3@+48
    0x00, 0x47,  # +42: BX r0
    0x00, 0x00,  # +44: padding
    0x00, 0x00,  # +46: padding
    # pool3 @ +48
    *u32le(ENGLISH_RESUME_GBA),
])
assert len(trampoline) == 0x4C, f"size={len(trampoline)}"
print(f"트램폴린: {len(trampoline)} bytes")

# ============================================================
# 5. 훅 패치 (8 bytes at 0x038AC)
# ============================================================
TRAMPOLINE_THUMB = TRAMPOLINE_GBA | 1
hook_patch = bytearray([
    0x00, 0x48,  # LDR r0, [PC, #0]
    0x00, 0x47,  # BX r0
    *u32le(TRAMPOLINE_THUMB),
])
assert len(hook_patch) == 8

# ============================================================
# 6. ROM 패치 적용
# ============================================================
with open(ROM_PATH, "rb") as f:
    rom = bytearray(f.read())

orig = rom[HOOK_ROM_OFF:HOOK_ROM_OFF+4]
print(f"훅 위치 ROM[038AC]: {orig.hex()} (기대: 30 b5 04 1c)")

area = rom[TRAMPOLINE_ROM_OFF:TRAMPOLINE_ROM_OFF+0x100]
print(f"트램폴린 영역 비FF: {sum(1 for b in area if b!=0xFF)}개 (기대: 0)")

rom[HOOK_ROM_OFF : HOOK_ROM_OFF+8] = hook_patch
rom[TRAMPOLINE_ROM_OFF : TRAMPOLINE_ROM_OFF+len(trampoline)] = trampoline
rom[GLYPH_ROM_OFF : GLYPH_ROM_OFF+len(glyph_data)] = glyph_data

with open(OUT_ROM, "wb") as f:
    f.write(rom)

print(f"\nROM 출력: {OUT_ROM}")
print(f"  훅    @ 0x{HOOK_ROM_OFF:06X}: {bytes(hook_patch).hex()}")
print(f"  트램  @ 0x{TRAMPOLINE_ROM_OFF:06X}: {bytes(trampoline[:16]).hex()}...")
print(f"  글리프 @ 0x{GLYPH_ROM_OFF:06X}: {len(glyph_data)} bytes")
