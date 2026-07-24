import struct

rom_path = r"D:\Works\zoe\Zone of the Enders - The Fist of Mars (USA).gba"
with open(rom_path, 'rb') as f:
    data = f.read()

def disasm_thumb(data, start, end):
    i = start
    while i < end:
        instr = struct.unpack_from('<H', data, i)[0]
        desc = ""
        step = 2

        if (instr & 0xF800) == 0x4800:
            rd = (instr >> 8) & 7
            imm8 = instr & 0xFF
            ptarget = (i + 4 + imm8 * 4) & 0xFFFFFFFC
            if ptarget + 4 <= len(data):
                val = struct.unpack_from('<I', data, ptarget)[0]
                desc = f"LDR r{rd}, [PC] => 0x{val:08X}"
        elif (instr & 0xF800) == 0x2000:
            desc = f"MOV r{(instr>>8)&7}, #0x{instr&0xFF:02X}"
        elif (instr & 0xF800) == 0x2800:
            desc = f"CMP r{(instr>>8)&7}, #0x{instr&0xFF:02X}"
        elif (instr & 0xF800) == 0x3000:
            desc = f"ADD r{(instr>>8)&7}, #0x{instr&0xFF:02X}"
        elif (instr & 0xF800) == 0x3800:
            desc = f"SUB r{(instr>>8)&7}, #0x{instr&0xFF:02X}"
        elif (instr & 0xF800) == 0x0000 and (instr>>6)&0x1F:
            desc = f"LSL r{instr&7}, r{(instr>>3)&7}, #{(instr>>6)&0x1F}"
        elif (instr & 0xF800) == 0x0800:
            desc = f"LSR r{instr&7}, r{(instr>>3)&7}, #{(instr>>6)&0x1F}"
        elif (instr & 0xF800) == 0x1000:
            desc = f"ASR r{instr&7}, r{(instr>>3)&7}, #{(instr>>6)&0x1F}"
        elif (instr & 0xF800) == 0xF000:
            next_i = struct.unpack_from('<H', data, i+2)[0]
            if (next_i & 0xF800) == 0xF800:
                h1 = instr & 0x7FF; h2 = next_i & 0x7FF
                offset = (h1 << 12) | (h2 << 1)
                if h1 & 0x400: offset -= 0x800000
                target = (i + 4 + offset) & 0xFFFFFF
                desc = f"BL 0x{target:05X}"
                step = 4
        elif (instr & 0xF800) == 0xF800:
            desc = "(BL hi)"
        elif (instr & 0xF000) == 0xD000 and (instr & 0x0F00) != 0x0F00:
            cond = (instr >> 8) & 0xF
            off8 = instr & 0xFF
            if off8 & 0x80: off8 -= 0x100
            target = i + 4 + off8 * 2
            cnames = ["EQ","NE","CS","CC","MI","PL","VS","VC","HI","LS","GE","LT","GT","LE","",""]
            desc = f"B{cnames[cond]} 0x{target:05X}"
        elif (instr & 0xF800) == 0xE000:
            off11 = instr & 0x7FF
            if off11 & 0x400: off11 -= 0x800
            desc = f"B 0x{i+4+off11*2:05X}"
        elif (instr & 0xFF00) == 0xB500:
            rlist = [f"r{j}" for j in range(8) if (instr>>j)&1]
            desc = f"PUSH {{{','.join(rlist)},LR}}"
        elif (instr & 0xFF00) == 0xBD00:
            rlist = [f"r{j}" for j in range(8) if (instr>>j)&1]
            desc = f"POP {{{','.join(rlist)},PC}}"
        elif (instr & 0xFF00) == 0xB400:
            rlist = [f"r{j}" for j in range(8) if (instr>>j)&1]
            desc = f"PUSH {{{','.join(rlist)}}}"
        elif (instr & 0xFF00) == 0xBC00:
            rlist = [f"r{j}" for j in range(8) if (instr>>j)&1]
            desc = f"POP {{{','.join(rlist)}}}"
        elif (instr & 0xF800) == 0x7800:
            desc = f"LDRB r{instr&7}, [r{(instr>>3)&7}, #{(instr>>6)&0x1F}]"
        elif (instr & 0xF800) == 0x7000:
            desc = f"STRB r{instr&7}, [r{(instr>>3)&7}, #{(instr>>6)&0x1F}]"
        elif (instr & 0xF800) == 0x6800:
            desc = f"LDR r{instr&7}, [r{(instr>>3)&7}, #{((instr>>6)&0x1F)*4}]"
        elif (instr & 0xF800) == 0x6000:
            desc = f"STR r{instr&7}, [r{(instr>>3)&7}, #{((instr>>6)&0x1F)*4}]"
        elif (instr & 0xF800) == 0x8000:
            desc = f"STRH r{instr&7}, [r{(instr>>3)&7}, #{((instr>>6)&0x1F)*2}]"
        elif (instr & 0xF800) == 0x8800:
            desc = f"LDRH r{instr&7}, [r{(instr>>3)&7}, #{((instr>>6)&0x1F)*2}]"
        elif (instr & 0xFE00) == 0x1800:
            desc = f"ADD r{instr&7}, r{(instr>>3)&7}, r{(instr>>6)&7}"
        elif (instr & 0xFE00) == 0x1A00:
            desc = f"SUB r{instr&7}, r{(instr>>3)&7}, r{(instr>>6)&7}"
        elif (instr & 0xFFC0) == 0x4340:
            desc = f"MUL r{instr&7}, r{(instr>>3)&7}"
        elif (instr & 0xFFC0) == 0x4040:
            desc = f"LSR r{instr&7}, r{(instr>>3)&7}"
        elif (instr & 0xFFC0) == 0x4080:
            desc = f"LSL r{instr&7}, r{(instr>>3)&7}"
        elif (instr & 0xFFC0) == 0x4000:
            desc = f"AND r{instr&7}, r{(instr>>3)&7}"
        elif (instr & 0xFFC0) == 0x40C0:
            desc = f"ROR r{instr&7}, r{(instr>>3)&7}"
        elif (instr & 0xFFC0) == 0x4100:
            desc = f"ASL r{instr&7}, r{(instr>>3)&7}"
        elif (instr & 0xFFC0) == 0x4240:
            desc = f"NEG r{instr&7}, r{(instr>>3)&7}"
        elif (instr & 0xFFC0) == 0x4280:
            desc = f"CMP r{instr&7}, r{(instr>>3)&7}"
        elif (instr & 0xFFC0) == 0x4300:
            desc = f"ORR r{instr&7}, r{(instr>>3)&7}"
        elif (instr & 0xFFC0) == 0x43C0:
            desc = f"MVN r{instr&7}, r{(instr>>3)&7}"
        elif (instr & 0xFFC0) == 0x4380:
            desc = f"BIC r{instr&7}, r{(instr>>3)&7}"
        elif (instr & 0xFF00) == 0x4700:
            desc = f"BX r{(instr>>3)&0xF}"
        elif (instr & 0xFF00) == 0x4600:
            rd = (instr & 7) | ((instr >> 4) & 8)
            rs = (instr >> 3) & 0xF
            desc = f"MOV r{rd}, r{rs}"
        elif (instr & 0xFF87) == 0x4485:
            desc = f"ADD hi"
        elif (instr & 0xF800) == 0x5800:
            desc = f"LDR r{instr&7}, [r{(instr>>3)&7}, r{(instr>>6)&7}]"
        elif (instr & 0xF800) == 0x5000:
            desc = f"STR r{instr&7}, [r{(instr>>3)&7}, r{(instr>>6)&7}]"
        elif (instr & 0xF800) == 0x5200:
            desc = f"STRH r{instr&7}, [r{(instr>>3)&7}, r{(instr>>6)&7}]"
        elif (instr & 0xF800) == 0x5A00:
            desc = f"LDRH r{instr&7}, [r{(instr>>3)&7}, r{(instr>>6)&7}]"
        elif (instr & 0xF800) == 0x5C00:
            desc = f"LDRB r{instr&7}, [r{(instr>>3)&7}, r{(instr>>6)&7}]"
        elif (instr & 0xF800) == 0x5400:
            desc = f"STRB r{instr&7}, [r{(instr>>3)&7}, r{(instr>>6)&7}]"
        elif (instr & 0xF800) == 0x9800:
            desc = f"LDR r{(instr>>8)&7}, [SP, #{(instr&0xFF)*4}]"
        elif (instr & 0xF800) == 0x9000:
            desc = f"STR r{(instr>>8)&7}, [SP, #{(instr&0xFF)*4}]"
        elif (instr & 0xFE00) == 0xB000:
            imm = instr & 0x7F
            desc = f"{'SUB' if instr&0x80 else 'ADD'} SP, #{imm*4}"
        elif (instr & 0xFF00) == 0xC800:
            desc = f"LDMIA r{(instr>>8)&7}!, {{...}}"
        elif (instr & 0xFF00) == 0xC000:
            desc = f"STMIA r{(instr>>8)&7}!, {{...}}"

        print(f"0x{i:05X}: {instr:04X}  {desc}")
        i += step

disasm_thumb(data, 0x04100, 0x042A0)
