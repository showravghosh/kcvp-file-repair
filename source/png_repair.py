"""Partial repair of PNG pictures damaged by STOP/Djvu ransomware.

A PNG is one compressed stream. After the encrypted part the stream is picked up again at the next block start;
data that refers back into the lost part stays unknown. Screenshots and drawings usually become exact again a
few rows later, so their lower part can be restored. Photographs saved as PNG do not, and are refused.
"""
import os
import struct
import zlib

ENC_END = 5 + 0x25800
TRAILER = 334
ORDER = [16, 17, 18, 0, 8, 7, 9, 6, 10, 5, 11, 4, 12, 3, 13, 2, 14, 1, 15]
LBASE = [3, 4, 5, 6, 7, 8, 9, 10, 11, 13, 15, 17, 19, 23, 27, 31, 35, 43, 51, 59, 67, 83, 99, 115, 131, 163, 195, 227, 258]
LEXT = [0] * 8 + [1] * 4 + [2] * 4 + [3] * 4 + [4] * 4 + [5] * 4 + [0]
DBASE = [1, 2, 3, 4, 5, 7, 9, 13, 17, 25, 33, 49, 65, 97, 129, 193, 257, 385, 513, 769, 1025, 1537, 2049, 3073, 4097, 6145,
         8193, 12289, 16385, 24577]
DEXT = [0, 0, 0, 0, 1, 1, 2, 2, 3, 3, 4, 4, 5, 5, 6, 6, 7, 7, 8, 8, 9, 9, 10, 10, 11, 11, 12, 12, 13, 13]
MAX_OUT = 160 * 1024 * 1024


class Bad(Exception):
    pass


def surviving_stream(path):
    """compressed picture data that lies after the encrypted part, with the chunk framing removed"""
    end = os.path.getsize(path) - TRAILER
    with open(path, 'rb') as f:
        f.seek(ENC_END)
        buf = f.read(max(0, end - ENC_END))
    parts = []
    p = buf.find(b'IDAT')
    first = None
    while p >= 4:
        length = struct.unpack('>I', buf[p - 4:p])[0]
        e = p + 4 + length
        if e + 4 <= len(buf) and zlib.crc32(buf[p:e]) == struct.unpack('>I', buf[e:e + 4])[0]:
            if first is None:
                first = p
            parts.append(buf[p + 4:e])
            if buf[e + 8:e + 12] != b'IDAT':
                break
            p = e + 8
        else:
            p = buf.find(b'IDAT', p + 1)
    if first is None:
        q = buf.rfind(b'IEND')
        if q < 12:
            return b''
        return buf[:q - 8]
    return (buf[:first - 8] if first >= 8 else b'') + b''.join(parts)


class Inflater:
    def __init__(self, data):
        self.d = data
        self.nb = len(data) * 8

    def bits(self, p, n):
        if p + n > self.nb:
            raise Bad()
        d = self.d
        v = 0
        for i in range(n):
            q = p + i
            v |= ((d[q >> 3] >> (q & 7)) & 1) << i
        return v

    @staticmethod
    def build(lengths, complete=True):
        cnt = [0] * 16
        for n in lengths:
            cnt[n] += 1
        cnt[0] = 0
        left = 1
        for n in range(1, 16):
            left = left * 2 - cnt[n]
            if left < 0:
                raise Bad()
        if left > 0 and complete and sum(cnt) > 1:
            raise Bad()
        code = 0
        nxt = [0] * 16
        for n in range(1, 16):
            code = (code + cnt[n - 1]) << 1
            nxt[n] = code
        tab = {}
        for s, n in enumerate(lengths):
            if n:
                tab[(n, nxt[n])] = s
                nxt[n] += 1
        return tab

    def sym(self, tab, p):
        d, nb = self.d, self.nb
        code = 0
        for n in range(1, 16):
            if p >= nb:
                raise Bad()
            code = (code << 1) | ((d[p >> 3] >> (p & 7)) & 1)
            p += 1
            s = tab.get((n, code))
            if s is not None:
                return s, p
        raise Bad()

    def header(self, p):
        bits = self.bits
        if bits(p + 1, 2) != 2:
            raise Bad()
        p += 3
        hlit, hdist, hclen = bits(p, 5) + 257, bits(p + 5, 5) + 1, bits(p + 10, 4) + 4
        p += 14
        if hlit > 286 or hdist > 30:
            raise Bad()
        cl = [0] * 19
        for i in range(hclen):
            cl[ORDER[i]] = bits(p, 3)
            p += 3
        ct = self.build(cl)
        lens = []
        while len(lens) < hlit + hdist:
            s, p = self.sym(ct, p)
            if s < 16:
                lens.append(s)
            elif s == 16:
                if not lens:
                    raise Bad()
                lens += [lens[-1]] * (3 + bits(p, 2))
                p += 2
            elif s == 17:
                lens += [0] * (3 + bits(p, 3))
                p += 3
            else:
                lens += [0] * (11 + bits(p, 7))
                p += 7
        if len(lens) != hlit + hdist or lens[256] == 0:
            raise Bad()
        return self.build(lens[:hlit]), self.build(lens[hlit:], False), p

    def block(self, p, out, known, lit, dist, limit=MAX_OUT):
        sym, bits = self.sym, self.bits
        while True:
            s, p = sym(lit, p)
            if s < 256:
                out.append(s)
                known.append(1)
            elif s == 256:
                return p
            else:
                s -= 257
                if s >= 29:
                    raise Bad()
                n = LBASE[s] + bits(p, LEXT[s])
                p += LEXT[s]
                d, p = sym(dist, p)
                if d >= 30:
                    raise Bad()
                dd = DBASE[d] + bits(p, DEXT[d])
                p += DEXT[d]
                if dd > len(out) or len(out) > limit:
                    raise Bad()
                for _ in range(n):
                    out.append(out[-dd])
                    known.append(known[-dd])

    def find_start(self):
        for p in range(0, min(self.nb, 4000000)):
            try:
                lit, dist, q = self.header(p)
                out, known = bytearray(32768), bytearray(32768)
                q = self.block(q, out, known, lit, dist, 4000000)
                if len(out) - 32768 < 500:
                    continue
                if not self.bits(p, 1) and self.bits(q + 1, 2) == 2:
                    self.header(q)
                return p
            except Bad:
                continue
        return None

    def run(self):
        """-> (bytes, known flags) of everything after the first block start; raises Bad if the end is not reached"""
        p = self.find_start()
        if p is None:
            raise Bad()
        out, known = bytearray(32768), bytearray(32768)
        while True:
            final = self.bits(p, 1)
            typ = self.bits(p + 1, 2)
            if typ == 2:
                lit, dist, p = self.header(p)
                p = self.block(p, out, known, lit, dist)
            elif typ == 0:
                p = (p + 3 + 7) // 8 * 8
                n = self.bits(p, 16)
                p += 32
                out += self.d[p // 8:p // 8 + n]
                known += bytes([1]) * n
                p += n * 8
            else:
                raise Bad()
            if final:
                return out[32768:], known[32768:]


def find_stride(out, known):
    """row length in bytes (filter byte + pixels): every row starts with a filter type 0..4, counted from the end"""
    n = len(out)
    for s in range(8, min(40004, n // 6)):
        seen = good = 0
        k = 1
        ok = True
        while k * s <= n and k <= 300:
            i = n - k * s
            if known[i]:
                seen += 1
                if out[i] <= 4:
                    good += 1
                elif seen - good > 2:
                    ok = False
                    break
            k += 1
        if ok and seen >= 20 and good >= seen * 0.99:
            return s
    return 0


def unfilter(out, known, stride, bpp):
    """-> list of (row bytes, share of exact bytes)"""
    n = stride - 1
    rows = len(out) // stride
    base = len(out) - rows * stride
    prev = bytearray([128]) * n
    pok = bytearray(n)
    res = []
    for r in range(rows):
        o = base + r * stride
        ft = out[o] if known[o] else (4 if r else 1)
        if ft > 4:
            ft = 4
        cur = bytearray(n)
        ok = bytearray(n)
        for i in range(n):
            kx = known[o + 1 + i]
            x = out[o + 1 + i] if kx else 0
            if i >= bpp:
                a, ka = cur[i - bpp], ok[i - bpp]
                c, kc = prev[i - bpp], pok[i - bpp]
            else:
                a, ka, c, kc = 0, 1, 0, 1
            b, kb = prev[i], pok[i]
            if ft == 0:
                v, k = (x if kx else b), kx
            elif ft == 1:
                v, k = (x + a) & 255, kx and ka
            elif ft == 2:
                v, k = (x + b) & 255, kx and kb
            elif ft == 3:
                v, k = (x + ((a + b) >> 1)) & 255, kx and ka and kb
            else:
                pa, pb, pc = abs(b - c), abs(a - c), abs(a + b - 2 * c)
                v = (x + (a if pa <= pb and pa <= pc else b if pb <= pc else c)) & 255
                k = kx and ka and kb and kc
            cur[i] = v
            ok[i] = 1 if k else 0
        res.append((cur, sum(ok) / n))
        prev, pok = cur, ok
    return res


def analyse_png(path):
    end = os.path.getsize(path) - TRAILER
    left = end - ENC_END
    if left < 30000:
        return False, 0.0, 'Too little of the picture data is left'
    return True, 100.0 * left / end * 0.9, 'Screenshots and drawings only: the lower part can be restored (checked during repair)'


def repair_png(path, dst):
    data = surviving_stream(path)
    if len(data) < 20000:
        return False, 'Too little of the picture data is left'
    try:
        out, known = Inflater(data).run()
    except Bad:
        return False, 'The picture data could not be picked up after the damaged part'
    stride = find_stride(out, known)
    if not stride:
        return False, 'Row layout could not be worked out'
    n = stride - 1
    cands = [b for b in (4, 3) if n % b == 0] or [1]
    best = None
    for bpp in cands:
        rows = unfilter(out, known, stride, bpp)
        tail = rows[-40:]
        alpha = 1.0
        if bpp == 4:
            vals = [row[i] for row, _ in tail for i in range(3, n, 4 * 7)]
            alpha = sum(1 for v in vals if v == 255) / max(1, len(vals))
        score = (alpha if bpp == 4 else 0.9)
        if best is None or score > best[0]:
            best = (score, bpp, rows)
    _, bpp, rows = best
    # keep the rows from where they are exact again
    start = None
    for r in range(len(rows) - 5):
        if all(rows[r + j][1] >= 0.98 for j in range(6)):
            start = r
            break
    if start is None or len(rows) - start < 16:
        return False, 'Not a screenshot-type picture: the pixels cannot be rebuilt exactly'
    keep = rows[start:]
    width = n // bpp
    ctype = {4: 6, 3: 2, 1: 0}[bpp]
    raw = b''.join(b'\x00' + bytes(row) for row, _ in keep)

    def chunk(tag, body):
        return struct.pack('>I', len(body)) + tag + body + struct.pack('>I', zlib.crc32(tag + body))
    with open(dst, 'wb') as fo:
        fo.write(b'\x89PNG\r\n\x1a\n')
        fo.write(chunk(b'IHDR', struct.pack('>IIBBBBB', width, len(keep), 8, ctype, 0, 0, 0)))
        fo.write(chunk(b'IDAT', zlib.compress(raw, 6)))
        fo.write(chunk(b'IEND', b''))
    return True, 'Lower part restored: %d rows, %d pixels wide' % (len(keep), width)
