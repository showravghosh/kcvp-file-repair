"""Repair of audio and video files damaged by STOP/Djvu ransomware. Source files are only read."""
import sys, os, struct, shutil

ENC_END = 5 + 0x25800      # first 5 bytes plain, next 153600 bytes encrypted
TRAILER = 334              # bytes appended by the ransomware
CH = 8 * 1024 * 1024


def copy_range(fi, fo, start, end):
    fi.seek(start)
    left = end - start
    while left > 0:
        b = fi.read(min(CH, left))
        if not b:
            break
        fo.write(b)
        left -= len(b)


# ---------------------------------------------------------------- MP3
BR1 = [0, 32, 40, 48, 56, 64, 80, 96, 112, 128, 160, 192, 224, 256, 320]
BR2 = [0, 8, 16, 24, 32, 40, 48, 56, 64, 80, 96, 112, 128, 144, 160]
SR = {3: [44100, 48000, 32000], 2: [22050, 24000, 16000], 0: [11025, 12000, 8000]}


def mp3_flen(h):
    if h[0] != 0xFF or (h[1] & 0xE0) != 0xE0:
        return 0
    ver = (h[1] >> 3) & 3
    layer = (h[1] >> 1) & 3
    bri = h[2] >> 4
    sri = (h[2] >> 2) & 3
    pad = (h[2] >> 1) & 1
    if ver == 1 or layer != 1 or bri in (0, 15) or sri == 3:
        return 0
    sr = SR[ver][sri]
    if ver == 3:
        return 144000 * BR1[bri] // sr + pad
    return 72000 * BR2[bri] // sr + pad


def find_mp3_start(buf, need=6):
    n = len(buf)
    i = 0
    while True:
        i = buf.find(b'\xff', i)
        if i < 0 or i + 4 > n:
            return -1
        j, ok = i, 0
        key = None
        while ok < need and j + 4 <= n:
            L = mp3_flen(buf[j:j + 4])
            k = (buf[j + 1] & 0xFE, buf[j + 2] & 0x0C)
            if not L or (key is not None and k != key):
                break
            key = k
            j += L
            ok += 1
        if ok >= need:
            return i
        i += 1


def fix_mp3(src, dst, size, dry):
    end = size - TRAILER
    if end - ENC_END < 20000:
        return 'FAIL', 'too small (fully encrypted)'
    with open(src, 'rb') as fi:
        fi.seek(ENC_END)
        buf = fi.read(min(2 * 1024 * 1024, end - ENC_END))
        off = find_mp3_start(buf)
        if off < 0:
            return 'FAIL', 'no mp3 frames found'
        if dry:
            return 'OK', 'start+%d' % off
        with open(dst, 'wb') as fo:
            copy_range(fi, fo, ENC_END + off, end)
    return 'OK', 'lost first %d KB' % ((ENC_END + off) // 1024)


# ---------------------------------------------------------------- AAC (ADTS)
def adts_len(h):
    if h[0] != 0xFF or (h[1] & 0xF6) != 0xF0:
        return 0
    return ((h[3] & 3) << 11) | (h[4] << 3) | (h[5] >> 5)


def fix_aac(src, dst, size, dry):
    end = size - TRAILER
    with open(src, 'rb') as fi:
        fi.seek(ENC_END)
        buf = fi.read(min(1024 * 1024, max(0, end - ENC_END)))
        i = 0
        start = -1
        while True:
            i = buf.find(b'\xff', i)
            if i < 0 or i + 7 > len(buf):
                break
            j, ok = i, 0
            while ok < 6 and j + 7 <= len(buf):
                L = adts_len(buf[j:j + 7])
                if L < 7:
                    break
                j += L
                ok += 1
            if ok >= 6:
                start = i
                break
            i += 1
        if start < 0:
            return 'FAIL', 'no ADTS frames found'
        if dry:
            return 'OK', 'start+%d' % start
        with open(dst, 'wb') as fo:
            copy_range(fi, fo, ENC_END + start, end)
    return 'OK', 'lost first %d KB' % ((ENC_END + start) // 1024)


# ---------------------------------------------------------------- MPEG-PS (vob/mpg)
def fix_mpegps(src, dst, size, dry):
    end = size - TRAILER
    with open(src, 'rb') as fi:
        fi.seek(ENC_END)
        buf = fi.read(min(4 * 1024 * 1024, max(0, end - ENC_END)))
        i = 0
        start = -1
        while True:
            i = buf.find(b'\x00\x00\x01\xba', i)
            if i < 0:
                break
            # confirm with another pack header within the next 64 KB
            if buf.find(b'\x00\x00\x01\xba', i + 4, i + 65536) > 0:
                start = i
                break
            i += 4
        if start < 0:
            return 'FAIL', 'no MPEG pack headers found'
        if dry:
            return 'OK', 'start+%d' % start
        with open(dst, 'wb') as fo:
            copy_range(fi, fo, ENC_END + start, end)
    return 'OK', 'lost first %d KB' % ((ENC_END + start) // 1024)


# ---------------------------------------------------------------- MP4 family
CONT = {b'moov', b'trak', b'mdia', b'minf', b'stbl', b'edts', b'udta', b'mvex'}


def walk(buf, start, end, depth=0):
    """yield (type, payload_start, payload_end) for boxes, recursing into containers"""
    p = start
    while p + 8 <= end:
        sz, typ = struct.unpack('>I4s', buf[p:p + 8])
        hl = 8
        if sz == 1:
            if p + 16 > end:
                return
            sz = struct.unpack('>Q', buf[p + 8:p + 16])[0]
            hl = 16
        elif sz == 0:
            sz = end - p
        if sz < hl or p + sz > end:
            return
        yield typ, p + hl, p + sz
        if typ in CONT:
            for x in walk(buf, p + hl, p + sz, depth + 1):
                yield x
        p += sz


def moov_ok(buf):
    """buf = whole moov box. returns (ok, min_chunk_offset, ntracks)"""
    sz = struct.unpack('>I', buf[:4])[0]
    if sz != len(buf):
        return False, 0, 0
    kinds = [t for t, a, b in walk(buf, 0, len(buf))]
    if b'mvhd' not in kinds or b'trak' not in kinds:
        return False, 0, 0
    mn = None
    for t, a, b in walk(buf, 0, len(buf)):
        if t == b'stco':
            n = struct.unpack('>I', buf[a + 4:a + 8])[0]
            if n and a + 8 + 4 * n <= b:
                v = min(struct.unpack('>%dI' % n, buf[a + 8:a + 8 + 4 * n]))
                mn = v if mn is None else min(mn, v)
        elif t == b'co64':
            n = struct.unpack('>I', buf[a + 4:a + 8])[0]
            if n and a + 8 + 8 * n <= b:
                v = min(struct.unpack('>%dQ' % n, buf[a + 8:a + 8 + 8 * n]))
                mn = v if mn is None else min(mn, v)
    if mn is None:
        return False, 0, 0
    return True, mn, kinds.count(b'trak')


def find_moov(fi, end, deep=True):
    """search for a valid moov box located after the encrypted area"""
    # 1) tail first, 2) then whole file
    def scan(lo, hi):
        pos = lo
        carry = b''
        fi.seek(lo)
        while pos < hi:
            b = fi.read(min(CH, hi - pos))
            if not b:
                break
            data = carry + b
            base = pos - len(carry)
            i = 0
            while True:
                i = data.find(b'moov', i)
                if i < 0:
                    break
                bp = base + i - 4
                if bp >= ENC_END:
                    here = fi.tell()
                    fi.seek(bp)
                    h = fi.read(4)
                    sz = struct.unpack('>I', h)[0]
                    if 100 < sz <= end - bp and sz < 400 * 1024 * 1024:
                        fi.seek(bp)
                        mv = fi.read(sz)
                        ok, mn, nt = moov_ok(mv)
                        if ok:
                            return bp, sz, mn, nt
                    fi.seek(here)
                i += 4
            carry = data[-8:]
            pos += len(b)
        return None
    tail = max(ENC_END - 8, end - 64 * 1024 * 1024)
    r = scan(tail, end)
    if r is None and deep and tail > ENC_END:
        r = scan(ENC_END - 8, tail + 16)
    return r


BRAND = {'.mp4': b'isom', '.m4v': b'isom', '.3gp': b'3gp4', '.m4a': b'M4A ', '.mov': b'qt  '}


def fix_mp4(src, dst, size, dry, ext):
    end = size - TRAILER
    with open(src, 'rb') as fi:
        r = find_moov(fi, end)
        if r is None:
            return 'FAIL', 'index (moov) was at the start of the file and is destroyed'
        mp, msz, mn, nt = r
        if mn >= mp:
            return 'FAIL', 'unexpected layout (media data after index)'
        big = (mp - 16) >= 2 ** 32
        hl = 16 if big else 8
        if mn >= 24 + hl:
            fs = 24
        elif mn >= 16 + hl:
            fs = 16
        else:
            return 'FAIL', 'no room for header (first chunk at %d)' % mn
        br = BRAND.get(ext, b'isom')
        ftyp = struct.pack('>I4s4sI', fs, b'ftyp', br, 0x200) + (br + b'mp42' if fs == 24 else b'')
        ftyp = ftyp[:fs]
        if big:
            mdat = struct.pack('>I4sQ', 1, b'mdat', mp - fs)
        else:
            mdat = struct.pack('>I4s', mp - fs, b'mdat')
        head = ftyp + mdat
        lost = max(0, ENC_END - mn)
        note = '%d track(s); first %d KB of media damaged' % (nt, lost // 1024)
        if dry:
            return 'OK', note
        with open(dst, 'wb') as fo:
            fo.write(head)
            copy_range(fi, fo, len(head), end)
    return 'OK', note


HANDLERS = {'.mp3': fix_mp3, '.aac': fix_aac, '.vob': fix_mpegps, '.mpg': fix_mpegps, '.mpeg': fix_mpegps,
            '.mp4': fix_mp4, '.3gp': fix_mp4, '.m4a': fix_mp4, '.mov': fix_mp4, '.m4v': fix_mp4}
