"""Analysis and repair engine for files damaged by STOP/Djvu ransomware (.kcvp and its sibling extensions).

The ransomware encrypts only the first 153,600 bytes of each file (after a 5 byte plain prefix) and appends a
334 byte trailer. This engine measures that damage and rebuilds a usable file from the part that was left
untouched. It never decrypts anything and it never writes to, renames or deletes a source file.
"""
import os
import re
import sys
import math
import shutil
import struct
import tempfile
import subprocess
import collections

import djvu_media
import mp4_clean
import extra_formats

ENC_START = 5
ENC_END = 5 + 0x25800
TRAILER = 334
MARKER = b'{36A698B9-D67C-4E07-BE82-0EC5B14B4DF5}'

JPEG_EXT = {'.jpg', '.jpeg', '.jpe'}
MP4_EXT = {'.mp4', '.3gp', '.m4a', '.mov', '.m4v'}
STREAM_EXT = {'.mp3': djvu_media.fix_mp3, '.aac': djvu_media.fix_aac, '.vob': djvu_media.fix_mpegps,
              '.mpg': djvu_media.fix_mpegps, '.mpeg': djvu_media.fix_mpegps}
NO_WINDOW = 0x08000000 if os.name == 'nt' else 0


def resource(*parts):
    base = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, *parts)


JFIX = resource('bin', 'jfix.exe' if os.name == 'nt' else 'jfix')


class Item:
    """One damaged file and what is known about it."""

    def __init__(self, path, root):
        self.path = path
        self.rel = os.path.relpath(path, root) if root and os.path.isdir(root) else os.path.basename(path)
        self.size = os.path.getsize(path)
        self.orig_name = os.path.splitext(os.path.basename(path))[0]
        self.ext = os.path.splitext(self.orig_name)[1].lower()
        self.kind = ''
        self.encrypted_pct = 0.0
        self.recover_pct = 0.0
        self.repairable = False
        self.note = ''
        self.result = ''          # filled by repair: 'Repaired', 'Failed', 'Skipped'
        self.jpeg = None          # analysis values for JPEG files
        self.out_suffix = ''

    @property
    def orig_size(self):
        return max(0, self.size - TRAILER)

    def out_rel(self):
        return os.path.join(os.path.dirname(self.rel), self.orig_name + self.out_suffix)


def is_djvu(path):
    """True when the file carries the STOP/Djvu trailer marker."""
    try:
        size = os.path.getsize(path)
        if size < TRAILER + 6:
            return False
        with open(path, 'rb') as f:
            f.seek(size - len(MARKER))
            return f.read(len(MARKER)) == MARKER
    except OSError:
        return False


def scan(source, subfolders=True, skip_dir=None, stop=None):
    """Yield paths of damaged files under a folder, or the single file itself."""
    if os.path.isfile(source):
        if is_djvu(source):
            yield source
        return
    skip = os.path.normcase(os.path.abspath(skip_dir)) if skip_dir else None
    for root, dirs, files in os.walk(source):
        if stop and stop():
            return
        if skip:
            dirs[:] = [d for d in dirs if os.path.normcase(os.path.abspath(os.path.join(root, d))) != skip]
        if not subfolders:
            dirs[:] = []
        for name in files:
            p = os.path.join(root, name)
            if is_djvu(p):
                yield p


# ---------------------------------------------------------------- JPEG

def find_jpeg_header(d):
    """Offset of a complete JPEG header (tables, frame, scan) that survived inside the intact part, or -1."""
    i = 0
    lim = min(len(d), 3000000)
    while True:
        i = d.find(b'\xff\xdb\x00', i, lim)
        if i < 0:
            return -1
        p = i
        seen = set()
        ok = False
        while p + 4 <= len(d) and d[p] == 0xFF:
            m = d[p + 1]
            length = (d[p + 2] << 8) | d[p + 3]
            if m in (0xDB, 0xC4, 0xC0, 0xC1, 0xC2, 0xDD, 0xFE) or 0xE0 <= m <= 0xEF:
                seen.add(m)
                if m == 0xDB and length not in (67, 132, 197):
                    break
                p += 2 + length
            elif m == 0xDA:
                ok = 0xDB in seen and 0xC4 in seen and bool(seen & {0xC0, 0xC1, 0xC2}) and length in (8, 12)
                break
            else:
                break
        if ok:
            return i
        i += 3


def read_tail(path):
    size = os.path.getsize(path)
    end = size - TRAILER
    with open(path, 'rb') as f:
        f.seek(ENC_END)
        return f.read(max(0, end - ENC_END))


def run_jfix(tail_bytes, out_path, qdc, workdir):
    tail = os.path.join(workdir, 'tail.bin')
    with open(tail, 'wb') as f:
        f.write(tail_bytes)
    tmp_out = '-' if out_path is None else os.path.join(workdir, 'out.jpg')
    args = [JFIX, tail, tmp_out] + ([str(qdc)] if qdc else [])
    try:
        r = subprocess.run(args, capture_output=True, text=True, timeout=300, creationflags=NO_WINDOW)
        line = (r.stdout.strip().splitlines() or ['status=FAIL reason=crash'])[-1]
    except (subprocess.TimeoutExpired, OSError) as e:
        line = 'status=FAIL reason=%s' % type(e).__name__
    d = dict(x.split('=', 1) for x in line.split() if '=' in x)
    if out_path is not None and d.get('status') == 'OK' and os.path.exists(tmp_out):
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        shutil.move(tmp_out, out_path)
    return d


JPEG_REASONS = {
    'not-baseline-or-multiscan': 'Progressive photo: the main picture data was encrypted',
    'cannot-decode(custom-huffman-or-unknown-layout)': 'Photo uses custom coding tables that were encrypted',
    'too-little-data': 'Too little of the picture is left',
    'no-end-marker': 'Picture data is incomplete',
}


def analyze_jpeg(item, workdir):
    if item.orig_size - ENC_END < 3000:
        item.note = 'Whole file is encrypted (smaller than 150 KB)'
        return
    tail = read_tail(item.path)
    h = find_jpeg_header(tail)
    if h >= 0:
        item.jpeg = {'mode': 'header', 'at': h}
        item.repairable = True
        item.recover_pct = 100.0
        item.note = 'Full picture (its header survived)'
        return
    d = run_jfix(tail, None, 0, workdir)
    if d.get('status') != 'OK':
        item.note = JPEG_REASONS.get(d.get('reason', ''), 'Picture data cannot be decoded')
        return
    w, h2, lost = int(d['W']), int(d['H']), float(d['lostpct'])
    if max(w, h2) > 2.4 * min(w, h2) or lost > 75:
        item.note = 'Too little of the picture is left'
        return
    item.jpeg = {'mode': 'rebuild', 'W': w, 'H': h2, 'ny': d['ny'], 'sugq': float(d['sugq']), 'bpp': float(d['bpp'])}
    item.repairable = True
    item.recover_pct = 100.0 - lost
    item.note = '%dx%d, top %.0f%% of the picture lost' % (w, h2, lost)


def _pattern(name):
    k = re.sub(r'[0-9]+', '#', os.path.splitext(name)[0])
    return re.sub(r'[a-f#]{12,}', 'HEX', k)[:24]


def assign_jpeg_quality(items):
    """Choose the DC quantiser for every rebuilt JPEG.

    The original tables are lost. Photos from one camera share them, and the brightness range of a photo gives
    an upper bound for the quantiser, so photos are grouped by name pattern and size and the levels that many
    photos sit just above are taken as the real ones.
    """
    groups = collections.defaultdict(list)
    for it in items:
        j = it.jpeg
        if j and j['mode'] == 'rebuild':
            key = (_pattern(it.orig_name),) + tuple(sorted((j['W'], j['H']))) + (j['ny'],)
            j['key'] = key
            groups[key].append(j)
    levels = {}
    for key, v in groups.items():
        est = []
        need = max(3, int(len(v) * 0.02))
        sv = sorted(j['sugq'] for j in v)
        i = 0
        while i < len(sv):
            f = sv[i]
            q = max(1, min(40, int(math.floor(f * 1.03))))
            if sum(1 for s in sv if f <= s <= f * 1.12) >= need:
                est.append(q)
                i += 1
                while i < len(sv) and sv[i] < q * 1.45:
                    i += 1
            else:
                i += 1
        levels[key] = est
    for key, v in groups.items():
        for j in v:
            ub = max(1, min(40, int(math.floor(j['sugq'] * 1.03))))
            fit = [q for q in levels[key] if q <= ub]
            if fit:
                j['qdc'] = max(fit)
            else:
                k = {'4': 1.0, '2': 1.15, '1': 1.4}.get(j['ny'], 1.0)
                best = min(range(1, 41), key=lambda q: abs(math.log(max(j['bpp'], 0.01) / (4.5 * k * q ** -0.8))))
                j['qdc'] = max(1, min(ub, max(best, int(math.ceil(ub / 3.0)))))


def repair_jpeg(item, dst, workdir):
    tail = read_tail(item.path)
    j = item.jpeg
    if j['mode'] == 'header':
        with open(dst + '.part', 'wb') as f:
            f.write(b'\xff\xd8')
            f.write(tail[j['at']:])
        os.replace(dst + '.part', dst)
        return True, 'Full picture restored'
    d = run_jfix(tail, dst, j.get('qdc', 0), workdir)
    if d.get('status') == 'OK' and os.path.exists(dst):
        return True, 'Picture rebuilt (%.0f%% of it)' % item.recover_pct
    return False, 'Rebuild failed'


# ---------------------------------------------------------------- audio / video

def analyze_stream(item):
    end = item.orig_size
    if end - ENC_END < 20000:
        item.note = 'Whole file is encrypted (too small)'
        return
    try:
        st, note = STREAM_EXT[item.ext](item.path, None, item.size, True)
    except Exception as e:
        st, note = 'FAIL', 'Read error: %s' % type(e).__name__
    if st == 'OK':
        item.repairable = True
        item.recover_pct = 100.0 * (end - ENC_END) / end
        item.note = 'Plays from just after the damaged start'
    else:
        item.note = note[:1].upper() + note[1:]


def analyze_mp4(item):
    end = item.orig_size
    if end - ENC_END < 20000:
        item.note = 'Whole file is encrypted (too small)'
        return
    try:
        with open(item.path, 'rb') as f:
            r = djvu_media.find_moov(f, end, deep=False)
    except Exception as e:
        item.note = 'Read error: %s' % type(e).__name__
        return
    if r is None:
        item.note = 'Index was at the start of the file and is encrypted'
        return
    mp, msz, first_chunk, ntracks = r
    lost = max(0, ENC_END - first_chunk)
    item.repairable = True
    item.recover_pct = 100.0 * (mp - first_chunk - lost) / max(1, mp - first_chunk)
    item.note = '%d track(s); the first moments are lost' % ntracks


def repair_media(item, dst):
    tmp = dst + '.part'
    try:
        if item.ext in MP4_EXT:
            st, note = djvu_media.fix_mp4(item.path, tmp, item.size, False, item.ext)
        else:
            st, note = STREAM_EXT[item.ext](item.path, tmp, item.size, False)
        if st != 'OK':
            if os.path.exists(tmp):
                os.remove(tmp)
            return False, note
        os.replace(tmp, dst)
        if item.ext in MP4_EXT:
            try:
                st2, note2 = mp4_clean.process(dst, True)
                if st2 == 'OK' and 'already' not in note2:
                    note = 'Starts at the first clean keyframe'
            except Exception:
                note = 'Repaired (start not trimmed)'
        return True, note[:1].upper() + note[1:]
    except Exception as e:
        if os.path.exists(tmp):
            os.remove(tmp)
        return False, 'Error: %s' % type(e).__name__


# ---------------------------------------------------------------- public API

KIND_NAMES = {'photo': 'Photo', 'audio': 'Audio', 'video': 'Video', 'other': 'Other'}


def kind_of(ext):
    if ext in extra_formats.HANDLERS:
        return extra_formats.HANDLERS[ext][0]
    if ext in JPEG_EXT or ext in ('.png', '.gif', '.bmp', '.webp', '.tif', '.tiff'):
        return 'photo'
    if ext in ('.mp3', '.aac', '.m4a', '.wav', '.flac', '.ogg', '.wma'):
        return 'audio'
    if ext in MP4_EXT or ext in ('.vob', '.mpg', '.mpeg', '.mkv', '.avi', '.wmv', '.flv', '.webm'):
        return 'video'
    return 'other'


UNSUPPORTED = {
    '.png': 'PNG cannot be read without its beginning',
    '.gif': 'GIF cannot be read without its beginning',
    '.mkv': 'MKV header was encrypted',
}


def analyze(item, workdir):
    """Fill in the damage and recovery figures of one item."""
    item.kind = kind_of(item.ext)
    orig = item.orig_size
    enc = max(0, min(ENC_END, orig) - ENC_START)
    item.encrypted_pct = 100.0 * enc / orig if orig else 100.0
    try:
        if item.ext in JPEG_EXT:
            analyze_jpeg(item, workdir)
        elif item.ext in STREAM_EXT:
            analyze_stream(item)
        elif item.ext in MP4_EXT:
            analyze_mp4(item)
        elif orig <= ENC_END:
            item.note = 'Whole file is encrypted (smaller than 150 KB)'
        elif item.ext in extra_formats.HANDLERS:
            kind, fn, _, suffix = extra_formats.HANDLERS[item.ext]
            item.repairable, item.recover_pct, item.note = fn(item.path)
            item.out_suffix = suffix if item.repairable else ''
        else:
            item.note = UNSUPPORTED.get(item.ext, 'This file type cannot be rebuilt without its beginning')
    except Exception as e:
        item.repairable = False
        item.note = 'Analysis error: %s' % type(e).__name__
    return item


def repair(item, out_root, workdir):
    """Write the repaired copy of one item below out_root. Returns (ok, message, destination)."""
    dst = os.path.join(out_root, item.out_rel())
    if os.path.normcase(os.path.abspath(dst)) == os.path.normcase(os.path.abspath(item.path)):
        return False, 'Output would overwrite the source', dst
    if os.path.exists(dst):
        return True, 'Already exists, kept', dst
    os.makedirs(os.path.dirname(dst) or '.', exist_ok=True)
    if item.ext in JPEG_EXT:
        ok, msg = repair_jpeg(item, dst, workdir)
    elif item.ext in extra_formats.HANDLERS:
        try:
            ok, msg = extra_formats.HANDLERS[item.ext][2](item.path, dst + '.part')
        except Exception as e:
            ok, msg = False, 'Error: %s' % type(e).__name__
        if ok:
            os.replace(dst + '.part', dst)
        elif os.path.exists(dst + '.part'):
            os.remove(dst + '.part')
    else:
        ok, msg = repair_media(item, dst)
    return ok, msg, dst


def make_workdir():
    return tempfile.mkdtemp(prefix='kcvp_repair_')


def human(n):
    for unit in ('B', 'KB', 'MB', 'GB'):
        if n < 1024 or unit == 'GB':
            return ('%d %s' % (n, unit)) if unit == 'B' else ('%.1f %s' % (n, unit))
        n /= 1024.0
