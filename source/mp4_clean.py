"""Make a repaired MP4/3GP start cleanly: samples inside the damaged area are dropped and
playback begins at the first video keyframe after it. Only the index (moov) is rewritten."""
import sys, os, struct, bisect

ENC_END = 5 + 0x25800
CONT = {b'moov', b'trak', b'mdia', b'minf', b'stbl', b'edts', b'udta', b'dinf'}

class Box:
    def __init__(self, typ, data=None, kids=None):
        self.typ, self.data, self.kids = typ, data, kids

    def find(self, t):
        return [k for k in self.kids if k.typ == t]

    def one(self, t):
        r = self.find(t)
        return r[0] if r else None

    def ser(self):
        body = b''.join(k.ser() for k in self.kids) if self.kids is not None else self.data
        return struct.pack('>I4s', 8 + len(body), self.typ) + body


def parse(buf, a, b, typ):
    kids = []
    p = a
    while p + 8 <= b:
        sz, t = struct.unpack('>I4s', buf[p:p + 8])
        hl = 8
        if sz == 1:
            sz = struct.unpack('>Q', buf[p + 8:p + 16])[0]
            hl = 16
        if sz < hl or p + sz > b:
            raise ValueError('bad box in ' + typ.decode('latin1'))
        if t in CONT and typ != b'udta':
            kids.append(parse(buf, p + hl, p + sz, t))
        else:
            kids.append(Box(t, buf[p + hl:p + sz]))
        p += sz
    return Box(typ, None, kids)


def top_boxes(f, size):
    out = []
    p = 0
    while p + 8 <= size:
        f.seek(p)
        sz, t = struct.unpack('>I4s', f.read(8))
        if sz == 1:
            sz = struct.unpack('>Q', f.read(8))[0]
        if sz < 8 or p + sz > size:
            raise ValueError('bad top-level box')
        out.append((t, p, sz))
        p += sz
    if p != size:
        raise ValueError('trailing bytes')
    return out


class Track:
    pass


def load_track(trak):
    t = Track()
    t.trak = trak
    mdia = trak.one(b'mdia')
    t.mdhd = mdia.one(b'mdhd')
    v = t.mdhd.data[0]
    t.timescale = struct.unpack('>I', t.mdhd.data[20:24] if v == 1 else t.mdhd.data[12:16])[0]
    t.handler = mdia.one(b'hdlr').data[8:12]
    stbl = mdia.one(b'minf').one(b'stbl')
    t.stbl = stbl
    d = stbl.one(b'stsz').data
    uni, n = struct.unpack('>II', d[4:12])
    t.sizes = [uni] * n if uni else list(struct.unpack('>%dI' % n, d[12:12 + 4 * n]))
    t.uniform = uni
    n_s = len(t.sizes)
    co = stbl.one(b'stco')
    t.co64 = co is None
    if co is not None:
        n = struct.unpack('>I', co.data[4:8])[0]
        t.chunks = list(struct.unpack('>%dI' % n, co.data[8:8 + 4 * n]))
    else:
        co = stbl.one(b'co64')
        n = struct.unpack('>I', co.data[4:8])[0]
        t.chunks = list(struct.unpack('>%dQ' % n, co.data[8:8 + 8 * n]))
    d = stbl.one(b'stsc').data
    n = struct.unpack('>I', d[4:8])[0]
    runs = [struct.unpack('>III', d[8 + 12 * i:20 + 12 * i]) for i in range(n)]
    t.spc = []
    t.sdi = []
    for i, (first, spc, sdi) in enumerate(runs):
        last = runs[i + 1][0] if i + 1 < n else len(t.chunks) + 1
        for c in range(first, last):
            t.spc.append(spc)
            t.sdi.append(sdi)
    if len(t.spc) != len(t.chunks):
        raise ValueError('stsc/stco mismatch')
    # sample offsets
    t.off = []
    t.chunk_of = []
    s = 0
    for c, o in enumerate(t.chunks):
        for j in range(t.spc[c]):
            if s >= n_s:
                break
            t.off.append(o)
            t.chunk_of.append(c)
            o += t.sizes[s]
            s += 1
    if len(t.off) != n_s:
        raise ValueError('sample count mismatch')
    d = stbl.one(b'stts').data
    n = struct.unpack('>I', d[4:8])[0]
    t.stts = [struct.unpack('>II', d[8 + 8 * i:16 + 8 * i]) for i in range(n)]
    t.dts = []
    x = 0
    for cnt, delta in t.stts:
        for i in range(cnt):
            t.dts.append(x)
            x += delta
    t.total = x
    if len(t.dts) < n_s:
        raise ValueError('stts short')
    t.dts = t.dts[:n_s]
    ss = stbl.one(b'stss')
    if ss is not None:
        n = struct.unpack('>I', ss.data[4:8])[0]
        t.sync = list(struct.unpack('>%dI' % n, ss.data[8:8 + 4 * n]))
    else:
        t.sync = None
    ct = stbl.one(b'ctts')
    if ct is not None:
        n = struct.unpack('>I', ct.data[4:8])[0]
        fmt = '>Ii' if ct.data[0] == 1 else '>II'
        t.ctts = [struct.unpack(fmt, ct.data[8 + 8 * i:16 + 8 * i]) for i in range(n)]
        t.ctts_v = ct.data[0]
    else:
        t.ctts = None
    return t


def drop_runs(runs, k):
    out = []
    for cnt, val in runs:
        if k >= cnt:
            k -= cnt
            continue
        out.append((cnt - k, val))
        k = 0
    return out


def set_kid(parent, typ, data):
    for kid in parent.kids:
        if kid.typ == typ:
            kid.data = data
            return
    parent.kids.append(Box(typ, data))


def rebuild(t, k):
    """drop the first k samples of track t; returns new media duration"""
    stbl = t.stbl
    n = len(t.sizes) - k
    if t.uniform:
        stbl.one(b'stsz').data = struct.pack('>III', 0, t.uniform, n)
    else:
        stbl.one(b'stsz').data = struct.pack('>III', 0, 0, n) + struct.pack('>%dI' % n, *t.sizes[k:])
    stts = drop_runs(t.stts, k)
    stbl.one(b'stts').data = struct.pack('>II', 0, len(stts)) + b''.join(struct.pack('>II', *r) for r in stts)
    if t.ctts is not None:
        c = drop_runs(t.ctts, k)
        fmt = '>Ii' if t.ctts_v == 1 else '>II'
        stbl.one(b'ctts').data = struct.pack('>BBBBI', t.ctts_v, 0, 0, 0, len(c)) + b''.join(struct.pack(fmt, *r) for r in c)
    if t.sync is not None:
        s = [x - k for x in t.sync if x > k]
        stbl.one(b'stss').data = struct.pack('>II', 0, len(s)) + struct.pack('>%dI' % len(s), *s)
    # chunks
    c0 = t.chunk_of[k]
    first_in_chunk = k - sum(1 for i in range(max(0, k - t.spc[c0]), k) if t.chunk_of[i] == c0)
    used = k - first_in_chunk
    chunks = [t.off[k]] + t.chunks[c0 + 1:]
    spc = [t.spc[c0] - used] + t.spc[c0 + 1:]
    sdi = t.sdi[c0:]
    # last chunk may claim more samples than exist; clamp
    tot = 0
    for i in range(len(spc)):
        if tot + spc[i] > n:
            spc[i] = n - tot
        tot += spc[i]
    while spc and spc[-1] == 0:
        spc.pop(); chunks.pop(); sdi.pop()
    runs = []
    for i in range(len(spc)):
        if not runs or runs[-1][1] != spc[i] or runs[-1][2] != sdi[i]:
            runs.append((i + 1, spc[i], sdi[i]))
    stbl.one(b'stsc').data = struct.pack('>II', 0, len(runs)) + b''.join(struct.pack('>III', *r) for r in runs)
    if t.co64:
        stbl.one(b'co64').data = struct.pack('>II', 0, len(chunks)) + struct.pack('>%dQ' % len(chunks), *chunks)
    else:
        stbl.one(b'stco').data = struct.pack('>II', 0, len(chunks)) + struct.pack('>%dI' % len(chunks), *chunks)
    sd = stbl.one(b'sdtp')
    if sd is not None:
        sd.data = sd.data[:4] + sd.data[4 + k:]
    stbl.kids = [x for x in stbl.kids if x.typ not in (b'sbgp', b'sgpd', b'subs', b'stps', b'padb', b'stdp')]
    newdur = t.total - t.dts[k]
    d = bytearray(t.mdhd.data)
    if d[0] == 1:
        d[24:32] = struct.pack('>Q', newdur)
    else:
        d[16:20] = struct.pack('>I', newdur)
    t.mdhd.data = bytes(d)
    return newdur


def set_dur(box, dur, off0, off1):
    d = bytearray(box.data)
    if d[0] == 1:
        d[off1:off1 + 8] = struct.pack('>Q', dur)
    else:
        d[off0:off0 + 4] = struct.pack('>I', min(dur, 0xFFFFFFFF))
    box.data = bytes(d)


def nal_ok(f, off, size):
    """does the sample look like length-prefixed H.264/HEVC NAL units?"""
    f.seek(off)
    b = f.read(min(size, 4 * 1024 * 1024))
    p = 0
    while p + 4 <= len(b):
        L = struct.unpack('>I', b[p:p + 4])[0]
        if L == 0 or p + 4 + L > size:
            return False
        p += 4 + L
    return p == size or len(b) < size


def process(path, apply):
    size = os.path.getsize(path)
    with open(path, 'rb') as f:
        tops = top_boxes(f, size)
        kinds = [t for t, p, s in tops]
        if kinds.count(b'moov') != 1 or b'moof' in kinds:
            return 'SKIP', 'unusual layout'
        mi = kinds.index(b'moov')
        mp, msz = tops[mi][1], tops[mi][2]
        if any(t == b'mdat' for t, p, s in tops[mi + 1:]):
            return 'SKIP', 'media after index'
        f.seek(mp)
        raw = f.read(msz)
        f.seek(mp + msz)
        rest = f.read()
        moov = parse(raw, 8, msz, b'moov')
        if moov.one(b'mvex') is not None:
            return 'SKIP', 'fragmented'
        tracks = [load_track(tr) for tr in moov.find(b'trak')]
        mvhd = moov.one(b'mvhd')
        mts = struct.unpack('>I', mvhd.data[20:24] if mvhd.data[0] == 1 else mvhd.data[12:16])[0]
        if all(t.off and t.off[0] >= ENC_END for t in tracks if t.sizes):
            return 'OK', 'already clean'
        vid = [t for t in tracks if t.handler == b'vide' and t.sizes]
        cut = {}
        T = 0.0
        if vid:
            v = vid[0]
            cands = v.sync if v.sync is not None else range(1, len(v.sizes) + 1)
            k = None
            for s in cands:
                if v.off[s - 1] >= ENC_END:
                    k = s - 1
                    break
            if k is None:
                return 'FAIL', 'no keyframe after the damaged part'
            T = v.dts[k] / v.timescale
            cut[id(v)] = k
        for t in tracks:
            if id(t) in cut or not t.sizes:
                continue
            k = bisect.bisect_left(t.dts, int(T * t.timescale))
            while k < len(t.sizes) and t.off[k] < ENC_END:
                k += 1
            if k >= len(t.sizes):
                return 'FAIL', 'a track has no clean samples'
            if t.handler == b'vide' and t.sync is not None:
                later = [s - 1 for s in t.sync if s - 1 >= k]
                if not later:
                    return 'FAIL', 'no keyframe in second video track'
                k = later[0]
            cut[id(t)] = k
        note = []
        maxdur = 0
        for t in tracks:
            if not t.sizes:
                continue
            k = cut[id(t)]
            if t.handler == b'vide':
                good = nal_ok(f, t.off[k], t.sizes[k])
                note.append('video cut %.2fs (%d frames)%s' % (t.dts[k] / t.timescale, k, '' if good else ' [first frame check failed]'))
            first_cto = 0
            if t.ctts is not None:
                first_cto = drop_runs(t.ctts, k)[0][1]
            newdur = rebuild(t, k)
            mdur = newdur * mts // t.timescale
            maxdur = max(maxdur, mdur)
            set_dur(t.trak.one(b'tkhd'), mdur, 20, 28)
            elst = struct.pack('>IIIiHH', 0, 1, min(mdur, 0xFFFFFFFF), max(0, first_cto), 1, 0)
            t.trak.kids = [x for x in t.trak.kids if x.typ != b'edts']
            pos = 1 if t.trak.kids and t.trak.kids[0].typ == b'tkhd' else 0
            t.trak.kids.insert(pos, Box(b'edts', None, [Box(b'elst', elst)]))
        set_dur(mvhd, maxdur, 16, 24)
        new = moov.ser()
    if not apply:
        return 'OK', '; '.join(note) + ' (dry run)'
    with open(path, 'r+b') as f:
        f.seek(mp)
        f.write(new)
        f.write(rest)
        f.truncate()
    return 'OK', '; '.join(note)
