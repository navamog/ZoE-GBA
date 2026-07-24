"""Render a ROM region as a GBA tile grid PNG to locate font/graphics.
Usage: python tiledump.py <rom> <offset> <num_tiles> <bpp> <tiles_per_row> <out.png> [tile_h]
bpp: 1 or 4. tile is 8 wide, tile_h default 8.
"""
import sys
from PIL import Image

def render(data, off, ntiles, bpp, tpr, th=8):
    tw = 8
    rows = (ntiles + tpr - 1) // tpr
    img = Image.new('L', (tpr * tw, rows * th), 0)
    px = img.load()
    if bpp == 1:
        bytes_per_tile = th  # 1 byte per row
    else:
        bytes_per_tile = th * 4  # 4bpp: 4 bytes per row
    for t in range(ntiles):
        base = off + t * bytes_per_tile
        tx = (t % tpr) * tw
        ty = (t // tpr) * th
        for ry in range(th):
            if bpp == 1:
                b = data[base + ry] if base + ry < len(data) else 0
                for cx in range(8):
                    v = 255 if (b >> (7 - cx)) & 1 else 0
                    px[tx + cx, ty + ry] = v
            else:
                rowbase = base + ry * 4
                for cx in range(8):
                    bi = rowbase + cx // 2
                    bb = data[bi] if bi < len(data) else 0
                    nib = (bb & 0xf) if (cx % 2 == 0) else (bb >> 4)
                    px[tx + cx, ty + ry] = nib * 17
    return img

if __name__ == '__main__':
    data = open(sys.argv[1], 'rb').read()
    off = int(sys.argv[2], 0)
    ntiles = int(sys.argv[3], 0)
    bpp = int(sys.argv[4])
    tpr = int(sys.argv[5])
    out = sys.argv[6]
    th = int(sys.argv[7]) if len(sys.argv) > 7 else 8
    img = render(data, off, ntiles, bpp, tpr, th)
    img = img.resize((img.width * 3, img.height * 3), Image.NEAREST)
    img.save(out)
    print('wrote', out, img.size)
