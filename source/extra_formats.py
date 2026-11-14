"""Repair of further file types damaged by STOP/Djvu ransomware: transport streams, WAV, FLAC, BMP,
ZIP based files and PDF. Every function reads the damaged file and writes a new one; sources are never changed.

analyse functions return (repairable, recoverable_percent, note)
repair functions return (ok, note)
"""
import os
import re
import struct

import png_repair
import heic_repair

ENC_END = 5 + 0x25800
TRAILER = 334
CH = 8 * 1024 * 1024


def _copy(fi, fo, start, end):
    fi.seek(start)
    left = end - start
    while left > 0:
        b = fi.read(min(CH, left))
        if not b:
            break
        fo.write(b)
        left -= len(b)


def _share(path, start=ENC_END):
    end = os.path.getsize(path) - TRAILER
    return 100.0 * max(0, end - start) / end if end > 0 else 0.0


# ---------------------------------------------------------------- MPEG transport stream (.ts .mts .m2ts)

def _ts_layout(path):
    """(first packet offset, packet size) or None"""
    end = os.path.getsize(path) - TRAILER
    with open(path, 'rb') as f:
        f.seek(ENC_END)
        d = f.read(min(400000, max(0, end - ENC_END)))
    for size, lead in ((188, 0), (192, 4), (204, 0)):
        for o in range(0, min(len(d), size * 3)):
            if d[o] != 0x47:
                continue
            if all(o + k * size < len(d) and d[o + k * size] == 0x47 for k in range(1, 40)):
                if o - lead >= 0:
                    return ENC_END + o - lead, size
                return ENC_END + o - lead + size, size
    return None


def analyse_ts(path):
    lay = _ts_layout(path)
    if not lay:
        return False, 0.0, 'No transport stream packets found'
    return True, _share(path, lay[0]), 'Plays from just after the damaged start'


def repair_ts(path, dst):
    lay = _ts_layout(path)
    if not lay:
        return False, 'No transport stream packets found'
    start, size = lay
    end = os.path.getsize(path) - TRAILER
    end = start + (end - start) // size * size
    with open(path, 'rb') as fi, open(dst, 'wb') as fo:
        _copy(fi, fo, start, end)
    return True, 'Lost the first %d KB' % (start // 1024)


# ---------------------------------------------------------------- WAV (PCM)

def _wav_layout(path):
    end = os.path.getsize(path) - TRAILER
    start = ENC_END + (-(ENC_END - 44)) % 4          # sample boundary for 16 bit stereo and mono
    with open(path, 'rb') as f:
        f.seek(start)
        d = f.read(min(400000, max(0, end - start)))
    n = len(d) // 2
    if n < 2000:
        return None
    x = struct.unpack('<%dh' % n, d[:n * 2])
    a1 = sum(abs(x[i] - x[i - 1]) for i in range(2, n, 3))
    a2 = sum(abs(x[i] - x[i - 2]) for i in range(2, n, 3))
    same = sum(1 for i in range(0, n - 1, 2) if x[i] == x[i + 1])
    # stereo when neighbours two apart match better than direct neighbours, or both channels are identical
    channels = 2 if (a2 < a1 or same > 0.9 * (n // 2)) else 1
    return start, end, channels


def analyse_wav(path):
    lay = _wav_layout(path)
    if not lay:
        return False, 0.0, 'Too little sound data is left'
    return True, _share(path, lay[0]), 'Sound format assumed: 44.1 kHz, 16 bit, %s' % ('stereo' if lay[2] == 2 else 'mono')


def repair_wav(path, dst):
    lay = _wav_layout(path)
    if not lay:
        return False, 'Too little sound data is left'
    start, end, ch = lay
    rate, bits = 44100, 16
    block = ch * bits // 8
    n = (end - start) // block * block
    head = b'RIFF' + struct.pack('<I', 36 + n) + b'WAVEfmt ' + struct.pack('<IHHIIHH', 16, 1, ch, rate, rate * block, block, bits) \
        + b'data' + struct.pack('<I', n)
    with open(path, 'rb') as fi, open(dst, 'wb') as fo:
        fo.write(head)
        _copy(fi, fo, start, start + n)
    return True, 'Rebuilt as 44.1 kHz 16 bit %s; if the speed sounds wrong the original used another rate' % ('stereo' if ch == 2 else 'mono')


# ---------------------------------------------------------------- FLAC

def _crc8(data):
    c = 0
    for b in data:
        c ^= b
        for _ in range(8):
            c = ((c << 1) ^ 0x07) & 0xFF if c & 0x80 else (c << 1) & 0xFF
    return c


_FLAC_RATES = {1: 88200, 2: 176400, 3: 192000, 4: 8000, 5: 16000, 6: 22050, 7: 24000, 8: 32000, 9: 44100, 10: 48000, 11: 96000}
_FLAC_BITS = {1: 8, 2: 12, 4: 16, 5: 20, 6: 24}


def _flac_header(d, p):
    """parse a frame header at p -> (length, blocksize, rate, channels, bits) or None"""
    if p + 16 > len(d) or d[p] != 0xFF or (d[p + 1] & 0xFE) != 0xF8:
        return None
    bs_code, sr_code = d[p + 2] >> 4, d[p + 2] & 15
    ch_code, bits_code = d[p + 3] >> 4, (d[p + 3] >> 1) & 7
    if d[p + 3] & 1 or bs_code == 0 or sr_code == 15 or ch_code > 10 or bits_code in (3, 7):
        return None
    q = p + 4
    lead = d[q]
    extra = 0 if lead < 0x80 else 1 if lead < 0xE0 else 2 if lead < 0xF0 else 3 if lead < 0xF8 else 4 if lead < 0xFC else 5 if lead < 0xFE else 6
    if 0x80 <= lead < 0xC0:
        return None
    q += 1 + extra
    if bs_code == 6:
        bs = d[q] + 1
        q += 1
    elif bs_code == 7:
        bs = ((d[q] << 8) | d[q + 1]) + 1
        q += 2
    else:
        bs = 192 if bs_code == 1 else (576 << (bs_code - 2)) if bs_code <= 5 else (256 << (bs_code - 8))
    if sr_code == 12:
        rate = d[q] * 1000
        q += 1
    elif sr_code == 13:
        rate = (d[q] << 8) | d[q + 1]
        q += 2
    elif sr_code == 14:
        rate = ((d[q] << 8) | d[q + 1]) * 10
        q += 2
    else:
        rate = _FLAC_RATES.get(sr_code, 0)
    if q >= len(d) or _crc8(d[p:q]) != d[q]:
        return None
    return q + 1 - p, bs, rate, (ch_code + 1 if ch_code < 8 else 2), _FLAC_BITS.get(bits_code, 0)


def _flac_layout(path):
    end = os.path.getsize(path) - TRAILER
    with open(path, 'rb') as f:
        f.seek(ENC_END)
        d = f.read(min(2000000, max(0, end - ENC_END)))
    p = 0
    while True:
        p = d.find(b'\xff', p)
        if p < 0 or p + 16 > len(d):
            return None
        h = _flac_header(d, p)
        if h and h[2] and h[4]:
            # a second valid frame header must follow within the next 256 KB
            q = p + h[0]
            lim = min(len(d) - 16, p + 262144)
            while q < lim:
                q = d.find(b'\xff', q, lim)
                if q < 0:
                    break
                h2 = _flac_header(d, q)
                if h2 and h2[2:] == h[2:]:
                    return ENC_END + p, end, h
                q += 1
        p += 1


def analyse_flac(path):
    lay = _flac_layout(path)
    if not lay:
        return False, 0.0, 'No FLAC frames found (the stream needs its lost header)'
    return True, _share(path, lay[0]), 'Plays from just after the damaged start'


def repair_flac(path, dst):
    lay = _flac_layout(path)
    if not lay:
        return False, 'No FLAC frames found'
    start, end, (hl, bs, rate, ch, bits) = lay
    v = (rate << 44) | ((ch - 1) << 41) | ((bits - 1) << 36)          # total samples unknown (0)
    info = struct.pack('>HH', bs, bs) + bytes(6) + v.to_bytes(8, 'big') + bytes(16)
    with open(path, 'rb') as fi, open(dst, 'wb') as fo:
        fo.write(b'fLaC' + bytes([0x80, 0, 0, 34]) + info)
        _copy(fi, fo, start, end)
    return True, 'Lost the first %d KB' % (start // 1024)


# ---------------------------------------------------------------- BMP (24 bit, uncompressed)

def _bmp_layout(path):
    end = os.path.getsize(path) - TRAILER
    with open(path, 'rb') as f:
        f.seek(ENC_END)
        d = f.read(max(0, end - ENC_END))
    if len(d) < 30000:
        return None
    best = None
    step = max(1, len(d) // 6000)
    for s in range(48, min(24004, len(d) // 4), 4):
        acc = n = 0
        for i in range(s, len(d), step):
            acc += abs(d[i] - d[i - s])
            n += 1
        sc = acc / n
        if best is None or sc < best[0] - 0.01:
            best = (sc, s)
    stride = best[1]
    total = end - 54
    rows_total = int(round(total / stride))
    if rows_total < 8 or abs(total - rows_total * stride) > 8:
        return None
    first = (ENC_END - 54 + stride - 1) // stride
    skip = first * stride + 54 - ENC_END
    rows = (len(d) - skip) // stride
    return d, stride, stride // 3, rows_total, skip, rows


def analyse_bmp(path):
    lay = _bmp_layout(path)
    if not lay:
        return False, 0.0, 'Picture layout could not be worked out'
    d, stride, w, total, skip, rows = lay
    return True, 100.0 * rows / total, '%dx%d, bottom %.0f%% of the picture lost' % (w, total, 100.0 * (total - rows) / total)


def repair_bmp(path, dst):
    lay = _bmp_layout(path)
    if not lay:
        return False, 'Picture layout could not be worked out'
    d, stride, w, total, skip, rows = lay
    lost = total - rows
    head = b'BM' + struct.pack('<IHHI', 54 + total * stride, 0, 0, 54) + struct.pack('<IiiHHIIiiII', 40, w, total, 1, 24, 0, total * stride, 2835, 2835, 0, 0)
    with open(dst, 'wb') as fo:
        fo.write(head)
        fo.write(bytes([128]) * (lost * stride))          # rows are stored bottom-up: the lost ones come first
        fo.write(d[skip:skip + rows * stride])
    return True, 'Picture rebuilt (%.0f%% of it)' % (100.0 * rows / total)


# ---------------------------------------------------------------- ZIP based files

def _zip_entries(path):
    """central directory records that survive -> (records, cd_offset) ; record = (raw_cd, local_offset, csize, name)"""
    end = os.path.getsize(path) - TRAILER
    with open(path, 'rb') as f:
        back = min(end, 70000)
        f.seek(end - back)
        tail = f.read(back)
        i = tail.rfind(b'PK\x05\x06')
        if i < 0 or i + 22 > len(tail):
            return None
        n, cd_size, cd_off = struct.unpack('<HII', tail[i + 10:i + 20])
        if cd_off == 0xFFFFFFFF or n == 0xFFFF or cd_off + cd_size > end or cd_off < 4:
            return None
        f.seek(cd_off)
        cd = f.read(cd_size)
    out = []
    p = 0
    while p + 46 <= len(cd) and cd[p:p + 4] == b'PK\x01\x02':
        csize = struct.unpack('<I', cd[p + 20:p + 24])[0]
        nl, el, cl = struct.unpack('<HHH', cd[p + 28:p + 34])
        off = struct.unpack('<I', cd[p + 42:p + 46])[0]
        rec = cd[p:p + 46 + nl + el + cl]
        out.append((rec, off, csize, cd[p + 46:p + 46 + nl].decode('utf-8', 'replace')))
        p += 46 + nl + el + cl
    return out, cd_off


def analyse_zip(path, office=False):
    r = _zip_entries(path)
    if not r:
        return False, 0.0, 'Archive directory not found or archive too large (ZIP64)'
    recs, cd_off = r
    good = [x for x in recs if x[1] >= ENC_END]
    if not good:
        return False, 0.0, 'All entries were inside the encrypted part'
    tot = sum(x[2] for x in recs) or 1
    pct = 100.0 * sum(x[2] for x in good) / tot
    if office:
        return True, pct, '%d of %d internal parts survive; saved as a ZIP of those parts (the document itself will not open)' % (len(good), len(recs))
    return True, pct, '%d of %d files inside survive' % (len(good), len(recs))


def repair_zip(path, dst):
    r = _zip_entries(path)
    if not r:
        return False, 'Archive directory not found'
    recs, cd_off = r
    order = sorted(recs, key=lambda x: x[1])
    bounds = {x[1]: (order[i + 1][1] if i + 1 < len(order) else cd_off) for i, x in enumerate(order)}
    good = [x for x in order if x[1] >= ENC_END]
    if not good:
        return False, 'All entries were inside the encrypted part'
    with open(path, 'rb') as fi, open(dst, 'wb') as fo:
        new_cd = []
        for rec, off, csize, name in good:
            pos = fo.tell()
            _copy(fi, fo, off, bounds[off])
            new_cd.append(rec[:42] + struct.pack('<I', pos) + rec[46:])
        cd_pos = fo.tell()
        blob = b''.join(new_cd)
        fo.write(blob)
        fo.write(b'PK\x05\x06' + struct.pack('<HHHHIIH', 0, 0, len(good), len(good), len(blob), cd_pos, 0))
    return True, '%d of %d files inside recovered' % (len(good), len(recs))


# ---------------------------------------------------------------- PDF

def analyse_pdf(path):
    end = os.path.getsize(path) - TRAILER
    if end - ENC_END < 20000:
        return False, 0.0, 'Whole file is encrypted (too small)'
    with open(path, 'rb') as f:
        f.seek(max(ENC_END, end - 4096))
        tail = f.read()
    if b'startxref' not in tail and b'%%EOF' not in tail:
        return False, 0.0, 'Document end not found'
    return True, _share(path), 'Partial: pages stored in the first 150 KB are lost; some viewers may refuse the file'


_OBJ = re.compile(rb'(?<![0-9])([0-9]{1,7}) ([0-9]{1,5}) obj(?![a-zA-Z])')
_PAGE = re.compile(rb'/Type\s*/Page(?![a-zA-Z])')
_CATALOG = re.compile(rb'/Type\s*/Catalog')
_PARENT = re.compile(rb'/Parent\s+([0-9]+)\s+[0-9]+\s+R')


def repair_pdf(path, dst):
    """Blank the encrypted start so later objects keep their offsets. When the page tree itself was in the
    encrypted part, build a new one from the page objects that survive."""
    end = os.path.getsize(path) - TRAILER
    head = b'%PDF-1.4\n%\xe2\xe3\xcf\xd3\n'
    with open(path, 'rb') as fi:
        fi.seek(ENC_END)
        body = fi.read(end - ENC_END)
    objs = {}
    pages = []
    parents = []
    has_catalog = False
    for m in _OBJ.finditer(body):
        num = int(m.group(1))
        chunk = body[m.end():m.end() + 4096]
        k = chunk.find(b'endobj')
        if k >= 0:
            chunk = chunk[:k]
        objs[num] = (ENC_END + m.start(), int(m.group(2)))
        if _CATALOG.search(chunk):
            has_catalog = True
        elif _PAGE.search(chunk):
            pages.append(num)
            pm = _PARENT.search(chunk)
            if pm:
                parents.append(int(pm.group(1)))
    pages = [n for n in dict.fromkeys(pages) if n in objs]
    with open(dst, 'wb') as fo:
        fo.write(head)
        fo.write(b' ' * (ENC_END - len(head)))
        fo.write(body)
        if has_catalog or not pages:
            return True, 'Damaged start blanked; pages stored there are lost'
        lost_parents = [n for n in dict.fromkeys(parents) if n not in objs]
        top = max(objs) + 1
        root = lost_parents[0] if lost_parents else top
        cat = top + 1
        fo.write(b'\n')
        new = {}
        kids = b' '.join(b'%d %d R' % (n, objs[n][1]) for n in pages)
        new[root] = fo.tell()
        fo.write(b'%d 0 obj\n<< /Type /Pages /Count %d /MediaBox [0 0 595 842] /Kids [%s] >>\nendobj\n' % (root, len(pages), kids))
        for extra in lost_parents[1:]:
            new[extra] = fo.tell()
            fo.write(b'%d 0 obj\n<< /Type /Pages /Count 0 /Kids [] /Parent %d 0 R >>\nendobj\n' % (extra, root))
        new[cat] = fo.tell()
        fo.write(b'%d 0 obj\n<< /Type /Catalog /Pages %d 0 R >>\nendobj\n' % (cat, root))
        table = dict(objs)
        for n, o in new.items():
            table[n] = (o, 0)
        size = max(table) + 1
        xref = fo.tell()
        fo.write(b'xref\n0 %d\n' % size)
        fo.write(b'0000000000 65535 f \n')
        for n in range(1, size):
            if n in table:
                fo.write(b'%010d %05d n \n' % table[n])
            else:
                fo.write(b'0000000000 65535 f \n')
        fo.write(b'trailer\n<< /Size %d /Root %d 0 R >>\nstartxref\n%d\n%%%%EOF\n' % (size, cat, xref))
    return True, 'Page list rebuilt: %d pages found after the damaged start' % len(pages)


OFFICE = {'.docx', '.xlsx', '.pptx', '.odt', '.ods', '.odp', '.docm', '.xlsm', '.pptm'}
ZIPS = {'.zip', '.jar', '.apk', '.epub', '.cbz', '.kmz'}

# extension -> (kind, analyse, repair, output suffix)
HANDLERS = {}
for _e in ('.ts', '.mts', '.m2ts', '.m2t', '.tp'):
    HANDLERS[_e] = ('video', analyse_ts, repair_ts, '')
HANDLERS['.wav'] = ('audio', analyse_wav, repair_wav, '')
HANDLERS['.flac'] = ('audio', analyse_flac, repair_flac, '')
HANDLERS['.bmp'] = ('photo', analyse_bmp, repair_bmp, '')
HANDLERS['.pdf'] = ('other', analyse_pdf, repair_pdf, '')
for _e in ZIPS:
    HANDLERS[_e] = ('other', analyse_zip, repair_zip, '')
for _e in OFFICE:
    HANDLERS[_e] = ('other', lambda p: analyse_zip(p, True), repair_zip, '.surviving_parts.zip')
HANDLERS['.png'] = ('photo', png_repair.analyse_png, png_repair.repair_png, '')
for _e in ('.heic', '.heif'):
    HANDLERS[_e] = ('photo', heic_repair.analyse_heic, heic_repair.repair_heic, '')
