"""ARM Thumb 텍스트 렌더링 루프 디스어셈블러"""
import sys, io, struct
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

ROM = r"D:\Works\zoe\Zone of the Enders - The Fist of Mars (USA).gba"
with open(ROM, 'rb') as f:
    rom = f.read()

def u16(off): return struct.unpack_from('<H', rom, off)[0]
def u32(off): return struct.unpack_from('<I', rom, off)[0]

def disasm_thumb(start, end):
    """간단한 ARM Thumb 디스어셈블러 (주요 명령어만)"""
    i = start
    while i < end:
        w = u16(i)
        b15_12 = (w >> 12) & 0xF
        b15_11 = (w >> 11) & 0x1F
        b15_13 = (w >> 13) & 0x7
        b15_10 = (w >> 10) & 0x3F
        b15_8  = (w >> 8) & 0xFF

        addr = 0x08000000 + i  # GBA 주소

        if b15_11 == 0b11110:  # BL high
            hi = (w & 0x7FF) << 12
            lo_w = u16(i+2)
            lo = (lo_w & 0x7FF) << 1
            dest = (0x08000000 + i + 4 + hi + lo) & 0xFFFFFFFF
            # BL은 ARM Thumb에서 i에 PC+4 기준
            print(f"  {addr:08X}: {w:04X} {lo_w:04X}  BL 0x{dest:08X}")
            i += 4
            continue

        # 단일 16비트 명령어들
        if b15_11 == 0b11001:  # STR Rn, [Rn, #imm]
            rd = w & 7; rb = (w>>3)&7; imm = ((w>>6)&0x1F)*4
            print(f"  {addr:08X}: {w:04X}      STR r{rd}, [r{rb}, #{imm}]")
        elif b15_11 == 0b11000:  # LDR Rn, [Rn, #imm]
            rd = w & 7; rb = (w>>3)&7; imm = ((w>>6)&0x1F)*4
            print(f"  {addr:08X}: {w:04X}      LDR r{rd}, [r{rb}, #{imm}]")
        elif b15_11 == 0b10011:  # STR Rd, [SP, #imm]
            rd = (w>>8)&7; imm = (w&0xFF)*4
            print(f"  {addr:08X}: {w:04X}      STR r{rd}, [SP, #{imm}]")
        elif b15_11 == 0b10010:  # LDR Rd, [SP, #imm]
            rd = (w>>8)&7; imm = (w&0xFF)*4
            print(f"  {addr:08X}: {w:04X}      LDR r{rd}, [SP, #{imm}]")
        elif b15_11 == 0b10001:  # STR Rd, [PC+imm] — STRH?
            pass
        elif b15_12 == 0b1000:  # STRH/LDRH
            l = (w>>11)&1; rd = w&7; rb = (w>>3)&7; imm = ((w>>6)&0x1F)*2
            op = "LDRH" if l else "STRH"
            print(f"  {addr:08X}: {w:04X}      {op} r{rd}, [r{rb}, #{imm}]")
        elif b15_11 == 0b01000:  # LDR from pool
            rd = (w>>8)&7; imm = (w&0xFF)*4
            pc4 = (i+4) & ~2
            pool_addr = pc4 + imm
            val = u32(pool_addr - 0x08000000) if pool_addr >= 0x08000000 else u32(pool_addr)
            print(f"  {addr:08X}: {w:04X}      LDR r{rd}, [PC, #{imm}]  ; =0x{val:08X}")
        elif b15_13 == 0b101 and (w>>12)&3 == 0:  # ADD/SUB
            pass
        elif (w >> 13) == 0b001:  # Move/compare/add/subtract immediate
            op = ['MOV','CMP','ADD','SUB'][(w>>11)&3]
            rd = (w>>8)&7; imm = w&0xFF
            print(f"  {addr:08X}: {w:04X}      {op} r{rd}, #{imm}")
        elif (w >> 11) == 0b11010:  # B (conditional)
            cond = ['EQ','NE','CS','CC','MI','PL','VS','VC','HI','LS','GE','LT','GT','LE']
            c = (w>>8)&0xF
            offset = (w&0xFF)
            if offset >= 0x80: offset -= 0x100
            dest = addr + 4 + offset*2
            cn = cond[c] if c < 14 else '??'
            print(f"  {addr:08X}: {w:04X}      B{cn} 0x{dest:08X}")
        elif (w >> 11) == 0b11100:  # B (unconditional)
            offset = w & 0x7FF
            if offset >= 0x400: offset -= 0x800
            dest = addr + 4 + offset*2
            print(f"  {addr:08X}: {w:04X}      B 0x{dest:08X}")
        elif (w >> 8) == 0b01000111:  # BX
            rm = (w>>3)&0xF
            print(f"  {addr:08X}: {w:04X}      BX r{rm}")
        elif (w >> 8) == 0b01000110:  # MOV high reg
            rd = (w&7)|((w>>4)&8); rs = (w>>3)&0xF
            print(f"  {addr:08X}: {w:04X}      MOV r{rd}, r{rs}")
        elif (w >> 12) == 0b0101:  # LDR/STR register offset
            l = (w>>11)&1; b = (w>>10)&1; ro = (w>>6)&7; rb = (w>>3)&7; rd = w&7
            ops = [["STR","STRB"],["LDR","LDRB"]]
            print(f"  {addr:08X}: {w:04X}      {ops[l][b]} r{rd}, [r{rb}, r{ro}]")
        elif (w >> 12) == 0b0110:  # LDR/STR immediate word
            l = (w>>11)&1; imm = ((w>>6)&0x1F)*4; rb = (w>>3)&7; rd = w&7
            print(f"  {addr:08X}: {w:04X}      {'LDR' if l else 'STR'} r{rd}, [r{rb}, #{imm}]")
        elif (w >> 12) == 0b0111:  # LDRB/STRB immediate
            l = (w>>11)&1; imm = (w>>6)&0x1F; rb = (w>>3)&7; rd = w&7
            print(f"  {addr:08X}: {w:04X}      {'LDRB' if l else 'STRB'} r{rd}, [r{rb}, #{imm}]")
        elif (w >> 13) == 0:  # Data processing shifted register / Shift
            op = (w>>11)&3
            ops = ['LSL','LSR','ASR','???']
            rd = w&7; rs = (w>>3)&7; imm = (w>>6)&0x1F
            if imm or op < 3:
                print(f"  {addr:08X}: {w:04X}      {ops[op]} r{rd}, r{rs}, #{imm}")
            else:
                print(f"  {addr:08X}: {w:04X}      {w:016b}")
        elif (w >> 10) == 0b010000:  # ALU
            ops = ['AND','EOR','LSL','LSR','ASR','ADC','SBC','ROR','TST','NEG','CMP','CMN','ORR','MUL','BIC','MVN']
            op = (w>>6)&0xF; rd = w&7; rs = (w>>3)&7
            print(f"  {addr:08X}: {w:04X}      {ops[op]} r{rd}, r{rs}")
        elif (w >> 12) == 0b1011:  # PUSH/POP
            l = (w>>11)&1; r = (w>>8)&1; rl = w&0xFF
            regs = [f"r{j}" for j in range(8) if rl&(1<<j)]
            if r: regs.append("LR" if not l else "PC")
            print(f"  {addr:08X}: {w:04X}      {'POP' if l else 'PUSH'} {{{','.join(regs)}}}")
        elif (w >> 13) == 0b011:  # Load/store immediate half
            l = (w>>11)&1; imm = ((w>>6)&0x1F)*2; rb = (w>>3)&7; rd = w&7
            print(f"  {addr:08X}: {w:04X}      {'LDRH' if l else 'STRH'} r{rd}, [r{rb}, #{imm}]  *")
        else:
            print(f"  {addr:08X}: {w:04X}      ???")

        i += 2

# 렌더링 루프 디스어셈블 (0x03D98-0x03E88)
print("=== 텍스트 렌더링 루프 (0x03D98-0x03E88) ===")
disasm_thumb(0x03D98, 0x03E90)

# 문자 그리기 함수 실제 위치 (0x003900)
print("\n=== 문자 그리기 함수 (0x003900-0x003980) ===")
disasm_thumb(0x003900, 0x003980)

# BG 맵 쓰기 관련 부분 (0x003980-0x003AB0)
print("\n=== 렌더링 후반부 (0x003980-0x003AB0) ===")
disasm_thumb(0x003980, 0x003AB0)

# BL 목적지 계산 확인
# F7FF FD56 at 0x03E50 (PC = 0x03E52)
# H = sign_extend(0x7FF << 12)
hi = 0xF7FF & 0x7FF
if hi >= 0x400: hi -= 0x800
H = hi << 12

lo = 0xFD56 & 0x7FF
offset = H + (lo << 1)
pc = 0x03E52
dest = (0x08000000 + pc + 4 + offset) & 0xFFFFFFFF
print(f"\n  BL at 0x03E50 → destination: 0x{dest:08X} (ROM 0x{dest-0x08000000:06X})")
