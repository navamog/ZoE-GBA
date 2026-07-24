import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

ORIG = r"D:\Works\zoe\Zone of the Enders - The Fist of Mars (USA).gba"
with open(ORIG, 'rb') as f:
    rom = f.read()

# 문제 오프셋들 확인
offsets = [0x078992, 0x078A64, 0x078A94, 0x078AE3, 0x078B08]
for off in offsets:
    raw = rom[off:off+30]
    # Caesar +6 디코딩
    decoded = ''.join(chr(b+6) if 0x1A<=b<=0x78 else '?' for b in raw)
    print(f"ORIG[0x{off:06X}]: {raw[:20].hex()}")
    print(f"  decoded: {decoded[:30]}")
    print()
