"""Round-trip test: extracted raw_hex -> decode -> encode -> must equal raw bytes.
Proves the text codec is lossless (skill invariant: round-trip before editing).
"""
import json, re, sys

# byte -> char (decode); char -> byte (encode)
def build_tables():
    b2c = {}
    b2c[0x20] = ' '
    for b in range(0x21, 0x3b): b2c[b] = chr(ord('A') + b - 0x21)
    for b in range(0x3b, 0x55): b2c[b] = chr(ord('a') + b - 0x3b)
    c2b = {v: k for k, v in b2c.items()}
    return b2c, c2b

B2C, C2B = build_tables()
# 0x01 NN punctuation token map (display) — must be reversible
PUNCT = {0x12: '.', 0x13: ',', 0x17: "'", 0x0c: '!', 0x0d: '?'}
PUNCT_REV = {v: k for k, v in PUNCT.items()}

TOKEN_RE = re.compile(r'\{nl\}|\{name\}|\{var:[0-9a-f]{2}\}|\{c[0-9a-f]{2}\}|\{x[0-9a-f]{2}\}')

def decode(raw: bytes) -> str:
    out = []; i = 0; n = len(raw)
    while i < n:
        b = raw[i]
        if b in B2C: out.append(B2C[b]); i += 1; continue
        if b == 0x01 and i + 1 < n:
            nn = raw[i+1]
            if nn in PUNCT: out.append(PUNCT[nn])
            elif nn == 0x19: out.append('{nl}')
            elif nn == 0x1d: out.append('{name}')
            else: out.append('{c%02x}' % nn)
            i += 2; continue
        if b == 0x15 and i + 1 < n:
            out.append('{var:%02x}' % raw[i+1]); i += 2; continue
        out.append('{x%02x}' % b); i += 1
    return ''.join(out)

def encode(text: str) -> bytes:
    out = bytearray(); i = 0; n = len(text)
    while i < n:
        m = TOKEN_RE.match(text, i)
        if m:
            tok = m.group(0)
            if tok == '{nl}': out += bytes([0x01, 0x19])
            elif tok == '{name}': out += bytes([0x01, 0x1d])
            elif tok.startswith('{var:'): out += bytes([0x15, int(tok[5:7], 16)])
            elif tok.startswith('{c'): out += bytes([0x01, int(tok[2:4], 16)])
            elif tok.startswith('{x'): out += bytes([int(tok[2:4], 16)])
            i = m.end(); continue
        c = text[i]
        if c in PUNCT_REV: out += bytes([0x01, PUNCT_REV[c]])
        elif c in C2B: out += bytes([C2B[c]])
        else: raise ValueError(f'unencodable char {c!r} at {i}')
        i += 1
    return bytes(out)

def main():
    recs = json.load(open('assets/translations/raw/script.json', encoding='utf-8'))
    ok = bad = 0; fails = []
    for r in recs:
        raw = bytes.fromhex(r['raw_hex'])
        try:
            re_enc = encode(decode(raw))
        except Exception as e:
            bad += 1; fails.append((r['file_offset'], str(e))); continue
        if re_enc == raw: ok += 1
        else:
            bad += 1; fails.append((r['file_offset'], 'mismatch'))
    print(f'round-trip OK {ok} / {ok+bad}  ({bad} fail)')
    for off, why in fails[:10]:
        print('  FAIL', off, why)

if __name__ == '__main__':
    main()
