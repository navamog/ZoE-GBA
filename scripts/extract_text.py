"""Extract ZOE:FoM (USA) dialogue records to JSON.
Records are 0x1f-terminated strings of table-encoded bytes + control codes.
"""
import json, sys

ROM = sys.argv[1] if len(sys.argv) > 1 else "Zone of the Enders - The Fist of Mars (USA).gba"
OUT = sys.argv[2] if len(sys.argv) > 2 else "assets/translations/raw/script.json"
# Real text lives in 0x70000-0x17a000 (story dialogue 0x90000+, names/items/bios
# 0x70000-0x90000). Below 0x70000 is graphics data that decodes to noise.
S, E = 0x70000, 0x180000

# control code -> token. 0x01 NN punctuation/control:
PUNCT = {0x12: '.', 0x13: ',', 0x17: "'", 0x0c: '!', 0x0d: '?', 0x19: '{nl}',
         0x1d: '{name}'}

def ch(b):
    if b == 0x20: return ' '
    if 0x21 <= b <= 0x3a: return chr(ord('A') + b - 0x21)
    if 0x3b <= b <= 0x54: return chr(ord('a') + b - 0x3b)
    return None

def decode_record(d, off, end):
    """Decode bytes [off,end) into a text string with control tokens.
    Returns (text, letter_count, total_visible)."""
    out = []; i = off; letters = 0; vis = 0
    while i < end:
        b = d[i]
        c = ch(b)
        if c is not None:
            out.append(c); i += 1; vis += 1
            if c != ' ': letters += 1
            continue
        if b == 0x01 and i + 1 < end:
            nn = d[i + 1]
            out.append(PUNCT.get(nn, '{c%02x}' % nn)); i += 2; vis += 1
            if nn in (0x12, 0x13, 0x17, 0x0c, 0x0d): letters += 1
            continue
        if b == 0x15 and i + 1 < end:
            out.append('{var:%02x}' % d[i + 1]); i += 2; continue
        out.append('{x%02x}' % b); i += 1
    return ''.join(out), letters, vis

VOWELS = set('aeiouAEIOU')

def looks_real(text, letters, vis):
    if vis < 4 or letters < 3: return False
    if letters / max(vis, 1) < 0.45: return False
    if text.count('{x') > 0: return False  # any raw graphics byte -> reject
    # strip tokens, analyse the plain letters
    import re as _re
    plain = _re.sub(r'\{[^}]*\}', '', text)
    alpha = [c for c in plain if c.isalpha()]
    if len(alpha) < 3: return False
    # vowel fraction (English ~0.38); noise/random has very few
    vfrac = sum(1 for c in alpha if c in VOWELS) / len(alpha)
    if vfrac < 0.20: return False
    # mid-word uppercase (lowercase immediately followed by uppercase) = noise signal
    midcap = sum(1 for k in range(1, len(plain))
                 if plain[k].isupper() and plain[k-1].islower())
    if midcap > max(1, len(alpha) * 0.12): return False
    # require a space unless it is a short proper-noun-like label
    if ' ' not in plain and len(alpha) > 16: return False
    return True

def clean_runs(d):
    """Yield (start,end) maximal runs of text bytes. State machine that
    consumes the argument byte after 0x01 / 0x15 so embedded 0x00 etc. don't
    break the run. 0x1f stays inside a run as an internal record separator."""
    i = S
    while i < E:
        b = d[i]
        if b == 0x20 or 0x21 <= b <= 0x54 or b == 0x1f:
            start = i
            while i < E:
                b = d[i]
                if b == 0x20 or 0x21 <= b <= 0x54 or b == 0x1f:
                    i += 1
                elif b in (0x01, 0x15) and i + 1 < E:
                    i += 2
                else:
                    break
            yield start, i
        else:
            i += 1

def main():
    d = open(ROM, 'rb').read()
    records = []
    for rs, re_ in clean_runs(d):
        # split run into records on 0x1f
        seg = rs
        j = rs
        while j <= re_:
            if j == re_ or d[j] == 0x1f:
                if seg < j:
                    text, letters, vis = decode_record(d, seg, j)
                    if looks_real(text, letters, vis):
                        records.append({
                            'entry_id': len(records),
                            'file_offset': '%06x' % seg,
                            'raw_hex': d[seg:j].hex(),
                            'text': text,
                            'ko': '',
                            'status': 'untranslated',
                        })
                seg = j + 1
            j += 1
    import os
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    json.dump(records, open(OUT, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    total_chars = sum(len(r['text']) for r in records)
    print(f"extracted {len(records)} records, {total_chars} chars -> {OUT}")
    # sample
    for r in records[:3]:
        print(" ", r['file_offset'], repr(r['text'][:70]))

if __name__ == '__main__':
    main()
