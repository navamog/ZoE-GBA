"""Minimal GDB remote client for mGBA stub. Dump GBA memory regions."""
import socket, time, sys

class GDB:
    def __init__(self, host='127.0.0.1', port=2345):
        last = None
        for _ in range(40):
            s = socket.socket(); s.settimeout(10)
            try:
                s.connect((host, port))
                s.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                self.s = s
                break
            except Exception as e:
                last = e; s.close(); time.sleep(0.5)
        else:
            raise last
        # drain any greeting
        self.s.settimeout(0.5)
        try:
            while True:
                d = self.s.recv(4096)
                if not d: break
        except Exception:
            pass
        self.s.settimeout(10)
    def _cksum(self, data): return sum(data.encode()) & 0xff
    def send(self, cmd):
        pkt = f'${cmd}#{self._cksum(cmd):02x}'
        self.s.sendall(pkt.encode())
        # read ack '+'
        a = self.s.recv(1)
        return a
    def recv_pkt(self):
        buf = b''
        while b'#' not in buf or len(buf) < buf.find(b'#') + 3:
            try: d = self.s.recv(4096)
            except socket.timeout: break
            if not d: break
            buf += d
        # extract $...#xx
        if b'$' in buf:
            st = buf.index(b'$') + 1
            en = buf.index(b'#', st)
            self.s.sendall(b'+')
            return buf[st:en].decode(errors='replace')
        return ''
    def cmd(self, c):
        self.send(c); return self.recv_pkt()
    def interrupt(self):
        self.s.sendall(b'\x03'); time.sleep(0.2)
        try: return self.recv_pkt()
        except: return ''
    def cont_async(self):
        # send continue without waiting
        pkt = f'$c#{self._cksum("c"):02x}'; self.s.sendall(pkt.encode())
        try: self.s.recv(1)
        except: pass
    def read_mem(self, addr, length):
        out = bytearray()
        chunk = 0x200  # mGBA gdb stub max read per 'm' packet
        off = 0
        while off < length:
            n = min(chunk, length - off)
            r = self.cmd(f'm{addr+off:x},{n:x}')
            if not r or r.startswith('E'):
                out.extend(b'\x00'*n)
            else:
                out.extend(bytes.fromhex(r))
            off += n
        return bytes(out)

if __name__ == '__main__':
    runsec = float(sys.argv[1]) if len(sys.argv) > 1 else 12
    g = GDB()
    print('halt reason:', g.cmd('?'))
    g.cont_async()
    print(f'running {runsec}s...')
    time.sleep(runsec)
    print('interrupt:', g.interrupt()[:40])
    vram = g.read_mem(0x06000000, 0x18000)
    pal  = g.read_mem(0x05000000, 0x400)
    open('out/vram.bin','wb').write(vram)
    open('out/pal.bin','wb').write(pal)
    # also read DISPCNT and BG regs
    io = g.read_mem(0x04000000, 0x60)
    open('out/ioregs.bin','wb').write(io)
    print('dumped vram/pal/io. DISPCNT=%04x' % (io[0]|io[1]<<8))
    g.cont_async()
