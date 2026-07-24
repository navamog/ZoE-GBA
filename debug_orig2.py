import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

ORIG = r"D:\Works\zoe\Zone of the Enders - The Fist of Mars (USA).gba"
ZOE  = r"D:\Works\zoe\ZOE_Korean.gba"
with open(ORIG, 'rb') as f:
    orig = f.read()
with open(ZOE, 'rb') as f:
    zoe = f.read()

def null_size(rom, offset):
    i = offset
    while i < len(rom) and rom[i] != 0x00:
        if rom[i] <= 0x0F:
            i += 2
        else:
            i += 1
    return i - offset

# 대표 오프셋들
offsets = [0x0781C8, 0x078992, 0x078A64]
for off in offsets:
    orig_raw = orig[off:off+25]
    zoe_raw  = zoe[off:off+25]
    orig_sz = null_size(orig, off)
    zoe_sz  = null_size(zoe, off)
    print(f"[0x{off:06X}]")
    print(f"  ORIG bytes: {orig_raw[:20].hex()}, null_size={orig_sz}")
    print(f"  ZOE  bytes: {zoe_raw[:20].hex()}, null_size={zoe_sz}")
    print()

# 원본 ROM에서 첫 번째 null이 어디 있는지 (실제)
off = 0x0781C8
for j in range(1000):
    if orig[off+j] == 0x00:
        print(f"orig[0x0781C8] 첫 번째 0x00: offset+{j} = 0x{off+j:06X}")
        # 그 전후 바이트
        print(f"  바이트: ...{orig[off+j-2:off+j+4].hex()}")
        break
