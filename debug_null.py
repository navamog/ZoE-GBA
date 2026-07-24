import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

ROM = r"D:\Works\zoe\Zone of the Enders - The Fist of Mars (USA).gba"
with open(ROM, 'rb') as f:
    rom = f.read()

# 0x0781C8 주변 바이트 덤프
offset = 0x0781C8
print(f"=== ROM[0x{offset:06X}:+80] ===")
for i in range(0, 80, 16):
    hexbytes = ' '.join(f'{rom[offset+i+j]:02X}' for j in range(16) if offset+i+j < len(rom))
    ascii_str = ''.join(chr(rom[offset+i+j]+6) if 0x1A <= rom[offset+i+j] <= 0x78 else '.'
                       for j in range(16) if offset+i+j < len(rom))
    print(f"  {offset+i:06X}: {hexbytes:<48} |{ascii_str}|")

# 첫 번째 null 찾기
print(f"\n  첫 0x00 위치:", end=' ')
for j in range(600):
    if rom[offset+j] == 0x00:
        print(f"0x{offset+j:06X} (offset+{j})")
        break

# translate_and_encode.py가 읽는 OUT_ROM vs original 차이 확인
OUT_ROM = r"D:\Works\zoe\ZOE_Korean.gba"
with open(OUT_ROM, 'rb') as f:
    rom2 = f.read()

# 해당 위치에서 다른지 확인
diff = sum(1 for i in range(0x78000, 0x80000) if rom[i] != rom2[i])
print(f"\noriginal vs ZOE_Korean.gba 차이: {diff}바이트 (0x78000-0x80000)")

# translate_and_encode.py가 ZOE_Korean.gba를 읽는지 확인
print(f"\nROM[0x{offset:06X}] original: {rom[offset]:02X}, ZOE_Korean: {rom2[offset]:02X}")
