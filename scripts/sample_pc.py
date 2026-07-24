"""Rapidly sample PC while the operator advances dialogue (spamming X).
Records non-BIOS (game-code) PCs to find the text renderer's hot address."""
import importlib.util, time, sys
from collections import Counter
spec = importlib.util.spec_from_file_location("g", "scripts/gdbclient.py")
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
DUR = float(sys.argv[1]) if len(sys.argv) > 1 else 20

g = m.GDB(); g.cmd('?')
def pc():
    r = g.cmd('g'); return int.from_bytes(bytes.fromhex(r[15*8:16*8]), 'little')
# render current frame first
g.cont_async(); time.sleep(0.3); g.interrupt()
hist = Counter(); n = 0
t0 = time.time()
while time.time() - t0 < DUR:
    g.cont_async(); time.sleep(0.004); g.interrupt()
    p = pc(); n += 1
    # exclude BIOS (0x0-0x3fff)
    if p >= 0x4000:
        hist[p] += 1
print(f"samples {n}, non-bios {sum(hist.values())}")
for addr, c in hist.most_common(30):
    print(f"  {addr:08x}: {c}")
g.cont_async()
