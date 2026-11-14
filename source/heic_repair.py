"""Repair of iPhone HEIC photos damaged by STOP/Djvu ransomware.

An iPhone HEIC photo is a grid of small HEVC tiles. The description of the grid (the 'meta' box) sits at the start
of the file and is lost, but most tiles survive. The description is the same for every photo taken with the same
iPhone model at the same resolution, so it is taken from a healthy photo (the template) and its location table is
rewritten to point at the surviving tiles. Tiles that were inside the encrypted part are replaced by a copy of the
first surviving tile.

The template is looked for next to the damaged file: any healthy .heic/.heif file in the same folder.
"""
import os
import struct

ENC_END = 5 + 0x25800
TRAILER = 334
MARKER = b'{36A698B9-D67C-4E07-BE82-0EC5B14B4DF5}'


class Unsupported(Exception):
    pass


def _boxes(buf, a, b):
    p = a
    while p + 8 <= b:
        size, typ = struct.unpack('>I4s', buf[p:p + 8])
        head = 8
        if size == 1:
            size = struct.unpack('>Q', buf[p + 8:p + 16])[0]
            head = 16
        elif size == 0:
            size = b - p
        if size < head or p + size > b:
            return
        yield typ, p, p + head, p + size
        p += size


def _uint(buf, p, n):
    return int.from_bytes(buf[p:p + n], 'big') if n else 0


class Template:
    """ftyp + meta of a healthy photo, with everything needed to re-point its items"""

    def __init__(self, path):
        with open(path, 'rb') as f:
            self.buf = f.read()
        buf = self.buf
        self.meta = None
        for typ, p, body, end in _boxes(buf, 0, len(buf)):
            if typ == b'meta':
                self.meta = (p, body + 4, end)
                break
        if self.meta is None or buf[4:8] != b'ftyp':
            raise Unsupported('template is not a HEIC file')
        kids = {typ: (body, end) for typ, p, body, end in _boxes(buf, self.meta[1], self.meta[2])}
        for need in (b'iloc', b'iinf', b'iref', b'pitm'):
            if need not in kids:
                raise Unsupported('template has no %s box' % need.decode())
        # primary item
        body, end = kids[b'pitm']
        primary = _uint(buf, body + 4, 2 if buf[body] == 0 else 4)
        # item types
        self.types = {}
        body, end = kids[b'iinf']
        cnt_size = 2 if buf[body] == 0 else 4
        for typ, p, b2, e2 in _boxes(buf, body + 4 + cnt_size, end):
            if typ == b'infe':
                ver = buf[b2]
                if ver >= 2:
                    idn = 2 if ver == 2 else 4
                    self.types[_uint(buf, b2 + 4, idn)] = buf[b2 + 4 + idn + 2:b2 + 4 + idn + 6]
        # tiles of the primary grid, in display order
        body, end = kids[b'iref']
        idn = 2 if buf[body] == 0 else 4
        self.tiles = []
        for typ, p, b2, e2 in _boxes(buf, body + 4, end):
            if typ == b'dimg':
                src = _uint(buf, b2, idn)
                n = _uint(buf, b2 + idn, 2)
                ids = [_uint(buf, b2 + idn + 2 + i * idn, idn) for i in range(n)]
                if src == primary or not self.tiles:
                    self.tiles = ids
        if len(self.tiles) < 2:
            raise Unsupported('template is not a tiled (grid) photo')
        # location table
        body, end = kids[b'iloc']
        ver = buf[body]
        self.off_size, self.len_size = buf[body + 4] >> 4, buf[body + 4] & 15
        self.base_size, self.idx_size = buf[body + 5] >> 4, (buf[body + 5] & 15) if ver in (1, 2) else 0
        if self.off_size < 4 or self.len_size < 4:
            raise Unsupported('template uses a compact location table')
        p = body + 6
        cnt = _uint(buf, p, 2 if ver < 2 else 4)
        p += 2 if ver < 2 else 4
        self.items = {}          # id -> dict(method, base_pos, ext_pos, offset, length, extents)
        for _ in range(cnt):
            iid = _uint(buf, p, 2 if ver < 2 else 4)
            p += 2 if ver < 2 else 4
            method = 0
            if ver in (1, 2):
                method = _uint(buf, p, 2) & 15
                p += 2
            p += 2
            base_pos = p
            base = _uint(buf, p, self.base_size)
            p += self.base_size
            ext = _uint(buf, p, 2)
            p += 2
            first = None
            for e in range(ext):
                p += self.idx_size
                if first is None:
                    first = (p, base + _uint(buf, p, self.off_size), _uint(buf, p + self.off_size, self.len_size))
                p += self.off_size + self.len_size
            self.items[iid] = {'method': method, 'base_pos': base_pos, 'ext_pos': first[0] if first else None,
                               'offset': first[1] if first else 0, 'length': first[2] if first else 0, 'extents': ext}
        for t in self.tiles:
            if t not in self.items or self.items[t]['extents'] != 1 or self.items[t]['method'] != 0:
                raise Unsupported('template tiles are stored in an unusual way')
        last_tile = max(self.items[t]['offset'] for t in self.tiles)
        tiles = set(self.tiles)
        # picture items (thumbnail and the like) stored after the last tile: they follow the tiles in the damaged file too
        self.after = sum(1 for i, it in self.items.items() if i not in tiles and it['method'] == 0 and it['extents'] == 1
                         and self.types.get(i) == b'hvc1' and it['offset'] > last_tile)

    def build(self, tile_data, other):
        """-> bytes of ftyp+meta with the location table re-pointed.
        tile_data: {item id: (offset, length)}; other: {item id: (offset, length)} for the remaining file items"""
        out = bytearray(self.buf[:self.meta[2]])
        for iid, it in self.items.items():
            if it['method'] != 0 or it['ext_pos'] is None:
                continue
            off, length = tile_data.get(iid) or other.get(iid) or (0, 0)
            if self.base_size:
                out[it['base_pos']:it['base_pos'] + self.base_size] = bytes(self.base_size)
            q = it['ext_pos']
            out[q:q + self.off_size] = off.to_bytes(self.off_size, 'big')
            out[q + self.off_size:q + self.off_size + self.len_size] = length.to_bytes(self.len_size, 'big')
        return bytes(out)


def _is_damaged(path):
    try:
        with open(path, 'rb') as f:
            f.seek(-len(MARKER), 2)
            return f.read() == MARKER
    except OSError:
        return True


def find_template(path):
    folder = os.path.dirname(os.path.abspath(path))
    try:
        names = sorted(os.listdir(folder))
    except OSError:
        return None
    for name in names:
        if os.path.splitext(name)[1].lower() in ('.heic', '.heif'):
            p = os.path.join(folder, name)
            if os.path.isfile(p) and not _is_damaged(p):
                try:
                    return Template(p)
                except (Unsupported, OSError, struct.error, IndexError):
                    continue
    return None


def surviving_tiles(path):
    """(offset, length) of the HEVC picture units that follow the encrypted part, in file order"""
    end = os.path.getsize(path) - TRAILER
    with open(path, 'rb') as f:
        f.seek(ENC_END)
        d = f.read(max(0, end - ENC_END))

    def unit(p):
        if p + 6 > len(d):
            return 0
        n = struct.unpack('>I', d[p:p + 4])[0]
        b0, b1 = d[p + 4], d[p + 5]
        if 2 < n < 8000000 and p + 4 + n <= len(d) and not (b0 & 0x81) and ((b0 >> 1) & 63) in (1, 19, 20, 21) and b1 == 1:
            return 4 + n
        return 0
    p = 0
    while p < len(d) - 6:
        a = unit(p)
        if a and unit(p + a) and unit(p + a + unit(p + a)):
            break
        p += 1
    else:
        return []
    out = []
    while True:
        a = unit(p)
        if not a:
            break
        out.append((ENC_END + p, a))
        p += a
    return out


def analyse_heic(path):
    tpl = find_template(path)
    if tpl is None:
        return False, 0.0, 'Needs a healthy HEIC photo from the same iPhone in the same folder (used as template)'
    units = surviving_tiles(path)
    if tpl.after and len(units) > tpl.after:
        units = units[:-tpl.after]
    k = min(len(units), len(tpl.tiles))
    if k < 2:
        return False, 0.0, 'No picture tiles survive'
    return True, 100.0 * k / len(tpl.tiles), '%d of %d picture tiles survive; the lost ones are filled with a copy' % (k, len(tpl.tiles))


def repair_heic(path, dst):
    tpl = find_template(path)
    if tpl is None:
        return False, 'No healthy HEIC photo found in the same folder to use as template'
    units = surviving_tiles(path)
    if tpl.after and len(units) > tpl.after:
        units = units[:-tpl.after]
    n = len(tpl.tiles)
    units = units[-n:]
    k = len(units)
    if k < 2:
        return False, 'No picture tiles survive'
    head_len = tpl.meta[2]
    # new media data: first the template's own non-tile items (thumbnail, Exif ...), then the surviving tiles
    blob = bytearray()
    other = {}
    tiles = set(tpl.tiles)
    pos0 = head_len + 8
    for iid, it in tpl.items.items():
        if iid in tiles or it['method'] != 0 or it['extents'] != 1 or not it['length']:
            continue
        other[iid] = (pos0 + len(blob), it['length'])
        blob += tpl.buf[it['offset']:it['offset'] + it['length']]
    tile_data = {}
    with open(path, 'rb') as f:
        placed = []
        for off, length in units:
            f.seek(off)
            placed.append((pos0 + len(blob), length))
            blob += f.read(length)
    lost = n - k
    for i, iid in enumerate(tpl.tiles):
        tile_data[iid] = placed[i - lost] if i >= lost else placed[0]
    with open(dst, 'wb') as fo:
        fo.write(tpl.build(tile_data, other))
        fo.write(struct.pack('>I4s', 8 + len(blob), b'mdat'))
        fo.write(blob)
    return True, '%d of %d picture tiles restored' % (k, n)
