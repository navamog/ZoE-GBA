"""Single-step while operator HOLDS X. Capture all regs each step. Stop when the
BG3 char block changes (a new line composed) — the composer is in the steps just
before the change. Saves trace to out/adv_trace.txt."""
import importlib.util, time, sys, hashlib
spec = importlib.util.spec_from_file_location("g", "scripts/gdbclient.py")
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
MAXSTEP = int(sys.argv[1]) if len(sys.argv) > 1 else 120000

g = m.GDB(); g.cmd('?')
def step():
    g.s.sendall(f'$s#{g._cksum("s"):02x}'.encode())
    try: g.s.recv(1)
    except Exception: pass
    return g.recv_pkt()
def regs():
    r = g.cmd('g')
    return [int.from_bytes(bytes.fromhex(r[i:i+8]), 'little') for i in range(0, 16*8, 8)]
def cblk_hash():
    return hashlib.md5(g.read_mem(0x06008000, 0x4000)).hexdigest()[:8]

base_hash = cblk_hash()
print("base char hash", base_hash)
trace = []
g.s.settimeout(6)
changed_at = None
for i in range(MAXSTEP):
    step()
    rv = regs()
    trace.append(rv)
    if i % 3000 == 0 and i > 0:
        h = cblk_hash()
        print(f"step {i} pc={rv[15]:08x} cblk={h}")
        if h != base_hash:
            changed_at = i
            print("CHAR BLOCK CHANGED at step", i)
            # trace a little more then stop
            for _ in range(1500):
                step(); trace.append(regs())
            break
with open('out/adv_trace.txt', 'w') as f:
    for rv in trace:
        f.write(' '.join('%08x' % x for x in rv) + '\n')
print("wrote out/adv_trace.txt", len(trace), "steps, changed_at", changed_at)
g.cont_async()
