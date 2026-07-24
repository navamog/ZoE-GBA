import struct
import sys

rom_path = r"D:\Works\zoe\Zone of the Enders - The Fist of Mars (USA).gba"
with open(rom_path, 'rb') as f:
    data = f.read()

def dis1(data, i):
    instr = struct.unpack_from('<H', data, i)[0]
    step = 2
    desc = f"??? 0x{instr:04X}"
    if (instr & 0xF800) == 0x4800:
        rd = (instr >> 8) & 7; imm8 = instr & 0xFF
        pt = (i + 4 + imm8 * 4) & 0xFFFFFFFC
        if pt + 4 <= len(data):
            val = struct.unpack_from('<I', data, pt)[0]
            desc = f"LDR r{rd}, [PC] => 0x{val:08X}"
    elif (instr & 0xF800) == 0x2000: desc = f"MOV r{(instr>>8)&7}, #0x{instr&0xFF:02X}"
    elif (instr & 0xF800) == 0x2800: desc = f"CMP r{(instr>>8)&7}, #0x{instr&0xFF:02X}"
    elif (instr & 0xF800) == 0x3000: desc = f"ADD r{(instr>>8)&7}, #0x{instr&0xFF:02X}"
    elif (instr & 0xF800) == 0x3800: desc = f"SUB r{(instr>>8)&7}, #0x{instr&0xFF:02X}"
    elif (instr & 0xF800) == 0x0000 and (instr>>6)&0x1F: desc = f"LSL r{instr&7}, r{(instr>>3)&7}, #{(instr>>6)&0x1F}"
    elif (instr & 0xF800) == 0x0800: desc = f"LSR r{instr&7}, r{(instr>>3)&7}, #{(instr>>6)&0x1F}"
    elif (instr & 0xF800) == 0x1000: desc = f"ASR r{instr&7}, r{(instr>>3)&7}, #{(instr>>6)&0x1F}"
    elif (instr & 0xF800) == 0xF000:
        ni = struct.unpack_from('<H', data, i+2)[0]
        if (ni & 0xF800) == 0xF800:
            h1 = instr & 0x7FF; h2 = ni & 0x7FF
            off = (h1 << 12) | (h2 << 1)
            if h1 & 0x400: off -= 0x800000
            tgt = (i + 4 + off) & 0xFFFFFF
            desc = f"BL 0x{tgt:05X}"; step = 4
    elif (instr & 0xF800) == 0xF800: desc = "(BL hi)"
    elif (instr & 0xF000) == 0xD000 and (instr & 0x0F00) != 0x0F00:
        cond = (instr >> 8) & 0xF; off8 = instr & 0xFF
        if off8 & 0x80: off8 -= 0x100
        tgt = i + 4 + off8 * 2
        cn = ["EQ","NE","CS","CC","MI","PL","VS","VC","HI","LS","GE","LT","GT","LE","",""]
        desc = f"B{cn[cond]} 0x{tgt:05X}"
    elif (instr & 0xF800) == 0xE000:
        off11 = instr & 0x7FF
        if off11 & 0x400: off11 -= 0x800
        desc = f"B 0x{i+4+off11*2:05X}"
    elif (instr & 0xFF00) == 0xB500: desc = f"PUSH {{r...,LR}}"
    elif (instr & 0xFF00) == 0xBD00: desc = f"POP {{r...,PC}}"
    elif (instr & 0xFF00) == 0xB400: desc = f"PUSH {{r...}}"
    elif (instr & 0xFF00) == 0xBC00: desc = f"POP {{r...}}"
    elif (instr & 0xF800) == 0x7800: desc = f"LDRB r{instr&7}, [r{(instr>>3)&7}, #{(instr>>6)&0x1F}]"
    elif (instr & 0xF800) == 0x7000: desc = f"STRB r{instr&7}, [r{(instr>>3)&7}, #{(instr>>6)&0x1F}]"
    elif (instr & 0xF800) == 0x6800: desc = f"LDR r{instr&7}, [r{(instr>>3)&7}, #{((instr>>6)&0x1F)*4}]"
    elif (instr & 0xF800) == 0x6000: desc = f"STR r{instr&7}, [r{(instr>>3)&7}, #{((instr>>6)&0x1F)*4}]"
    elif (instr & 0xF800) == 0x8000: desc = f"STRH r{instr&7}, [r{(instr>>3)&7}, #{((instr>>6)&0x1F)*2}]"
    elif (instr & 0xF800) == 0x8800: desc = f"LDRH r{instr&7}, [r{(instr>>3)&7}, #{((instr>>6)&0x1F)*2}]"
    elif (instr & 0xFE00) == 0x1800: desc = f"ADD r{instr&7}, r{(instr>>3)&7}, r{(instr>>6)&7}"
    elif (instr & 0xFE00) == 0x1A00: desc = f"SUB r{instr&7}, r{(instr>>3)&7}, r{(instr>>6)&7}"
    elif (instr & 0xFE00) == 0x1C00: desc = f"ADD r{instr&7}, r{(instr>>3)&7}, #{(instr>>6)&7}"
    elif (instr & 0xFE00) == 0x1E00: desc = f"SUB r{instr&7}, r{(instr>>3)&7}, #{(instr>>6)&7}"
    elif (instr & 0xFFC0) == 0x4340: desc = f"MUL r{instr&7}, r{(instr>>3)&7}"
    elif (instr & 0xFFC0) == 0x4040: desc = f"LSR r{instr&7}, r{(instr>>3)&7}"
    elif (instr & 0xFFC0) == 0x4080: desc = f"LSL r{instr&7}, r{(instr>>3)&7}"
    elif (instr & 0xFFC0) == 0x4000: desc = f"AND r{instr&7}, r{(instr>>3)&7}"
    elif (instr & 0xFFC0) == 0x40C0: desc = f"ROR r{instr&7}, r{(instr>>3)&7}"
    elif (instr & 0xFFC0) == 0x4280: desc = f"CMP r{instr&7}, r{(instr>>3)&7}"
    elif (instr & 0xFFC0) == 0x4300: desc = f"ORR r{instr&7}, r{(instr>>3)&7}"
    elif (instr & 0xFFC0) == 0x43C0: desc = f"MVN r{instr&7}, r{(instr>>3)&7}"
    elif (instr & 0xFFC0) == 0x4380: desc = f"BIC r{instr&7}, r{(instr>>3)&7}"
    elif (instr & 0xFFC0) == 0x4240: desc = f"NEG r{instr&7}, r{(instr>>3)&7}"
    elif (instr & 0xFF00) == 0x4700: desc = f"BX r{(instr>>3)&0xF}"
    elif (instr & 0xFF00) == 0x4600:
        rd=(instr&7)|((instr>>4)&8); rs=(instr>>3)&0xF
        desc = f"MOV r{rd}, r{rs}"
    elif (instr & 0xF800) == 0x5800: desc = f"LDR r{instr&7}, [r{(instr>>3)&7}, r{(instr>>6)&7}]"
    elif (instr & 0xF800) == 0x5000: desc = f"STR r{instr&7}, [r{(instr>>3)&7}, r{(instr>>6)&7}]"
    elif (instr & 0xF800) == 0x5A00: desc = f"LDRH r{instr&7}, [r{(instr>>3)&7}, r{(instr>>6)&7}]"
    elif (instr & 0xF800) == 0x5C00: desc = f"LDRB r{instr&7}, [r{(instr>>3)&7}, r{(instr>>6)&7}]"
    elif (instr & 0xF800) == 0x5200: desc = f"STRH r{instr&7}, [r{(instr>>3)&7}, r{(instr>>6)&7}]"
    elif (instr & 0xF800) == 0x5400: desc = f"STRB r{instr&7}, [r{(instr>>3)&7}, r{(instr>>6)&7}]"
    elif (instr & 0xF800) == 0x9800: desc = f"LDR r{(instr>>8)&7}, [SP, #{(instr&0xFF)*4}]"
    elif (instr & 0xF800) == 0x9000: desc = f"STR r{(instr>>8)&7}, [SP, #{(instr&0xFF)*4}]"
    elif (instr & 0xFE00) == 0xB000: desc = f"{'SUB' if instr&0x80 else 'ADD'} SP, #{(instr&0x7F)*4}"
    elif (instr & 0xFF00) == 0x4400:
        rd=(instr&7)|((instr>>4)&8); rs=(instr>>3)&0xF
        desc = f"ADD r{rd}, r{rs} (hi)"
    elif instr == 0: desc = "NOP/data"
    return desc, step

start = int(sys.argv[1], 16) if len(sys.argv) > 1 else 0x00E80
end = int(sys.argv[2], 16) if len(sys.argv) > 2 else 0x01060

i = start
while i < end:
    d, s = dis1(data, i)
    print(f"0x{i:05X}: {struct.unpack_from('<H',data,i)[0]:04X}  {d}")
    i += s
