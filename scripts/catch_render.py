"""Connect GDB, set breakpoints on renderer candidates, continue, and log every
breakpoint hit with full registers. Meanwhile the operator presses X in mGBA to
advance dialogue, triggering the text renderer."""
import importlib.util, time, sys
spec = importlib.util.spec_from_file_location("g", "scripts/gdbclient.py")
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)

CANDS = [0x08000980]  # 1bpp glyph-plotter candidate (ROM)
DUR = float(sys.argv[1]) if len(sys.argv) > 1 else 45

g = m.GDB()
g.cmd('?')
def regs():
    r = g.cmd('g')
    return [int.from_bytes(bytes.fromhex(r[i:i+8]), 'little') for i in range(0, 17*8, 8)]
for a in CANDS:
    print("set bp", hex(a), g.cmd(f'Z0,{a&~1:x},2'))

log = open('out/render_hits.txt', 'w')
t0 = time.time()
hits = 0
while time.time() - t0 < DUR:
    g.cont_async(); g.s.settimeout(DUR)
    try:
        stop = g.recv_pkt()
    except Exception:
        stop = ''
    if not stop.startswith(('T', 'S')):
        log.write(f"timeout/no-hit ({stop!r})\n"); break
    rv = regs()
    line = f"hit pc={rv[15]:08x} " + ' '.join(f"r{i}={rv[i]:08x}" for i in range(13))
    log.write(line + "\n"); log.flush()
    hits += 1
    if hits >= 60:
        log.write("(stopping after 60 hits)\n"); break
log.write(f"total hits {hits}\n"); log.close()
print("done, hits", hits)
g.cont_async()
