"""KCVP File Repair - desktop window.

Select a folder or a single file damaged by STOP/Djvu ransomware (.kcvp and similar), see how much of each file
is encrypted and how much can be rebuilt, then write repaired copies to a folder of your choice.
"""
import os
import csv
import sys
import time
import queue
import shutil
import threading
import subprocess
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

import engine

APP_NAME = 'KCVP File Repair'
VERSION = '1.3.0'

BG = '#ffffff'
PANEL = '#ffffff'
LINE = '#d0d0d0'
TEXT = '#000000'
MUTED = '#444444'
ACCENT = '#0b57d0'
GOOD = '#0a6b2d'
BAD = '#a11b1b'
STEPS = ('Select', 'Analyze', 'Repair', 'Report')


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title('%s %s' % (APP_NAME, VERSION))
        self.geometry('1180x780')
        self.minsize(980, 660)
        self.configure(bg=BG)
        self.items = []
        self.queue = queue.Queue()
        self.worker = None
        self.stop_flag = threading.Event()
        self.started = 0.0
        self.phase = 'idle'
        self.step = 0
        self._style()
        self._build()
        self.protocol('WM_DELETE_WINDOW', self._close)
        self.after(100, self._poll)

    # ------------------------------------------------------------ look
    def _style(self):
        s = ttk.Style(self)
        try:
            s.theme_use('clam')
        except tk.TclError:
            pass
        base = ('Segoe UI', 10)
        s.configure('.', background=BG, foreground=TEXT, font=base, bordercolor=LINE, lightcolor=BG, darkcolor=BG)
        s.configure('TFrame', background=BG)
        s.configure('Card.TFrame', background=PANEL, relief='solid', borderwidth=1)
        s.configure('TLabel', background=BG, foreground=TEXT)
        s.configure('Card.TLabel', background=PANEL, foreground=TEXT)
        s.configure('Muted.TLabel', background=PANEL, foreground=MUTED)
        s.configure('Head.TLabel', background=PANEL, foreground=TEXT, font=('Segoe UI Semibold', 12))
        s.configure('Title.TLabel', background=BG, foreground=TEXT, font=('Segoe UI Semibold', 20))
        s.configure('Sub.TLabel', background=BG, foreground=MUTED, font=('Segoe UI', 10))
        s.configure('Big.TLabel', background=PANEL, foreground=TEXT, font=('Segoe UI Semibold', 30))
        s.configure('TCheckbutton', background=PANEL, foreground=TEXT)
        s.map('TCheckbutton', background=[('active', PANEL)])
        s.configure('TButton', background='#f2f2f2', foreground=TEXT, padding=(12, 6), bordercolor='#9a9a9a')
        s.map('TButton', background=[('active', '#e6e6e6'), ('disabled', '#f6f6f6')], foreground=[('disabled', '#8a8a8a')])
        s.configure('Primary.TButton', background=ACCENT, foreground='#ffffff', padding=(16, 8), bordercolor=ACCENT,
                    font=('Segoe UI Semibold', 10))
        s.map('Primary.TButton', background=[('active', '#0842a0'), ('disabled', '#b9c9e6')], foreground=[('disabled', '#ffffff')])
        s.configure('TEntry', fieldbackground='#ffffff', foreground=TEXT, bordercolor='#9a9a9a', padding=5)
        s.configure('Treeview', background='#ffffff', fieldbackground='#ffffff', foreground=TEXT, rowheight=24, bordercolor=LINE)
        s.configure('Treeview.Heading', background='#f2f2f2', foreground=TEXT, font=('Segoe UI Semibold', 10), bordercolor=LINE)
        s.map('Treeview', background=[('selected', '#dbe7fb')], foreground=[('selected', TEXT)])
        s.configure('Horizontal.TProgressbar', background=ACCENT, troughcolor='#e9e9e9', bordercolor='#e9e9e9',
                    lightcolor=ACCENT, darkcolor=ACCENT)
        s.configure('TCombobox', fieldbackground='#ffffff', foreground=TEXT)

    def _card(self, parent, **grid):
        f = ttk.Frame(parent, style='Card.TFrame', padding=14)
        f.grid(**grid)
        return f

    def _build(self):
        root = ttk.Frame(self, padding=(18, 12, 18, 8))
        root.pack(fill='both', expand=True)
        root.columnconfigure(0, weight=3)
        root.columnconfigure(1, weight=2)
        root.rowconfigure(3, weight=3)
        root.rowconfigure(4, weight=1)

        head = ttk.Frame(root)
        head.grid(row=0, column=0, columnspan=2, sticky='ew')
        ttk.Label(head, text=APP_NAME, style='Title.TLabel').pack(anchor='w')
        ttk.Label(head, style='Sub.TLabel',
                  text='Rebuilds the undamaged part of photos, audio and video hit by STOP/Djvu ransomware. '
                       'It repairs files; it does not decrypt them.').pack(anchor='w')

        self.steps = tk.Canvas(root, height=58, bg=BG, highlightthickness=0)
        self.steps.grid(row=1, column=0, columnspan=2, sticky='ew', pady=(10, 8))
        self.steps.bind('<Configure>', lambda e: self._draw_steps())

        # ---- selection card
        sel = self._card(root, row=2, column=0, sticky='nsew', padx=(0, 10))
        sel.columnconfigure(1, weight=1)
        ttk.Label(sel, text='1. Select files or folder', style='Head.TLabel').grid(row=0, column=0, columnspan=4, sticky='w')
        ttk.Label(sel, text='Damaged files', style='Card.TLabel').grid(row=1, column=0, sticky='w', pady=(10, 0))
        self.src = tk.StringVar()
        ttk.Entry(sel, textvariable=self.src).grid(row=1, column=1, sticky='ew', padx=8, pady=(10, 0))
        ttk.Button(sel, text='Folder...', command=self._pick_folder).grid(row=1, column=2, pady=(10, 0))
        ttk.Button(sel, text='File...', command=self._pick_file).grid(row=1, column=3, padx=(6, 0), pady=(10, 0))
        self.sub = tk.BooleanVar(value=True)
        ttk.Checkbutton(sel, text='Include subfolders', variable=self.sub).grid(row=2, column=1, sticky='w', padx=8, pady=(4, 0))
        ttk.Label(sel, text='Save repaired files to', style='Card.TLabel').grid(row=3, column=0, sticky='w', pady=(10, 0))
        self.out = tk.StringVar()
        ttk.Entry(sel, textvariable=self.out).grid(row=3, column=1, sticky='ew', padx=8, pady=(10, 0))
        ttk.Button(sel, text='Browse...', command=self._pick_out).grid(row=3, column=2, pady=(10, 0))
        ttk.Label(sel, style='Muted.TLabel',
                  text='The damaged files are only read. They are never changed, moved or deleted.').grid(
            row=4, column=0, columnspan=4, sticky='w', pady=(8, 0))
        btns = ttk.Frame(sel, style='Card.TFrame', borderwidth=0)
        btns.grid(row=5, column=0, columnspan=4, sticky='w', pady=(12, 0))
        self.b_an = ttk.Button(btns, text='Analyze', style='Primary.TButton', command=self._analyze)
        self.b_an.pack(side='left')
        self.b_rep = ttk.Button(btns, text='Repair', style='Primary.TButton', command=self._repair, state='disabled')
        self.b_rep.pack(side='left', padx=8)
        self.b_stop = ttk.Button(btns, text='Stop', command=self._stop, state='disabled')
        self.b_stop.pack(side='left')

        # ---- status card
        st = self._card(root, row=2, column=1, sticky='nsew')
        st.columnconfigure(1, weight=1)
        ttk.Label(st, text='Status', style='Head.TLabel').grid(row=0, column=0, columnspan=2, sticky='w')
        self.pct = tk.StringVar(value='0%')
        ttk.Label(st, textvariable=self.pct, style='Big.TLabel', width=5).grid(row=1, column=0, rowspan=4, sticky='w', pady=(6, 0))
        self.s_phase = tk.StringVar(value='Ready')
        self.s_found = tk.StringVar(value='Damaged files found: -')
        self.s_enc = tk.StringVar(value='Encrypted part: -')
        self.s_rec = tk.StringVar(value='Can be repaired: -')
        for i, v in enumerate((self.s_phase, self.s_found, self.s_enc, self.s_rec)):
            ttk.Label(st, textvariable=v, style='Card.TLabel').grid(row=1 + i, column=1, sticky='w', padx=(10, 0), pady=(6 if i == 0 else 1, 0))
        self.bar = ttk.Progressbar(st, mode='determinate', maximum=100)
        self.bar.grid(row=5, column=0, columnspan=2, sticky='ew', pady=(10, 6))
        self.s_time = tk.StringVar(value='')
        ttk.Label(st, textvariable=self.s_time, style='Muted.TLabel').grid(row=6, column=0, columnspan=2, sticky='w')
        self.b_open = ttk.Button(st, text='Open output folder', command=self._open_out, state='disabled')
        self.b_open.grid(row=7, column=0, columnspan=2, sticky='w', pady=(8, 0))

        # ---- table
        tb = self._card(root, row=3, column=0, columnspan=2, sticky='nsew', pady=(10, 0))
        tb.columnconfigure(0, weight=1)
        tb.rowconfigure(1, weight=1)
        top = ttk.Frame(tb, style='Card.TFrame', borderwidth=0)
        top.grid(row=0, column=0, columnspan=2, sticky='ew')
        ttk.Label(top, text='Files', style='Head.TLabel').pack(side='left')
        self.s_count = tk.StringVar(value='')
        ttk.Label(top, textvariable=self.s_count, style='Muted.TLabel').pack(side='left', padx=12)
        self.flt = tk.StringVar(value='All files')
        cb = ttk.Combobox(top, textvariable=self.flt, state='readonly', width=18,
                          values=('All files', 'Can be repaired', 'Cannot be repaired'))
        cb.pack(side='right')
        cb.bind('<<ComboboxSelected>>', lambda e: self._refill())
        ttk.Label(top, text='Show', style='Card.TLabel').pack(side='right', padx=6)
        cols = ('file', 'type', 'size', 'enc', 'rec', 'status')
        self.tree = ttk.Treeview(tb, columns=cols, show='headings', selectmode='browse')
        for c, t, w, a in (('file', 'File', 380, 'w'), ('type', 'Type', 70, 'w'), ('size', 'Size', 90, 'e'),
                           ('enc', 'Encrypted', 90, 'e'), ('rec', 'Recoverable', 100, 'e'), ('status', 'Details', 400, 'w')):
            self.tree.heading(c, text=t, anchor=a)
            self.tree.column(c, width=w, anchor=a, stretch=c in ('file', 'status'))
        self.tree.tag_configure('ok', foreground=TEXT)
        self.tree.tag_configure('no', foreground=MUTED)
        self.tree.tag_configure('fail', foreground=BAD)
        self.tree.grid(row=1, column=0, sticky='nsew', pady=(8, 0))
        sb = ttk.Scrollbar(tb, orient='vertical', command=self.tree.yview)
        sb.grid(row=1, column=1, sticky='ns', pady=(8, 0))
        self.tree.configure(yscrollcommand=sb.set)

        # ---- log
        lg = self._card(root, row=4, column=0, columnspan=2, sticky='nsew', pady=(10, 0))
        lg.columnconfigure(0, weight=1)
        lg.rowconfigure(1, weight=1)
        top2 = ttk.Frame(lg, style='Card.TFrame', borderwidth=0)
        top2.grid(row=0, column=0, columnspan=2, sticky='ew')
        ttk.Label(top2, text='Activity log', style='Head.TLabel').pack(side='left')
        ttk.Button(top2, text='Clear log', command=lambda: self._set_log('')).pack(side='right')
        self.b_csv = ttk.Button(top2, text='Save report...', command=self._save_report, state='disabled')
        self.b_csv.pack(side='right', padx=6)
        self.log = tk.Text(lg, height=6, bg='#ffffff', fg=TEXT, relief='flat', font=('Consolas', 9), wrap='none', state='disabled')
        self.log.grid(row=1, column=0, sticky='nsew', pady=(6, 0))
        sb2 = ttk.Scrollbar(lg, orient='vertical', command=self.log.yview)
        sb2.grid(row=1, column=1, sticky='ns', pady=(6, 0))
        self.log.configure(yscrollcommand=sb2.set)

        self.status = tk.StringVar(value='Ready')
        bar = tk.Frame(self, bg='#f2f2f2', highlightbackground=LINE, highlightthickness=1)
        bar.pack(fill='x', side='bottom')
        tk.Label(bar, textvariable=self.status, bg='#f2f2f2', fg=TEXT, anchor='w', font=('Segoe UI', 9)).pack(side='left', padx=10, pady=3)
        tk.Label(bar, text='%s  |  Version %s' % (APP_NAME, VERSION), bg='#f2f2f2', fg=MUTED, font=('Segoe UI', 9)).pack(side='right', padx=10)

    def _draw_steps(self):
        c = self.steps
        c.delete('all')
        w = max(c.winfo_width(), 400)
        n = len(STEPS)
        gap = w / n
        for i, name in enumerate(STEPS):
            x = gap * i + gap / 2
            done, cur = i < self.step, i == self.step
            if i:
                c.create_line(x - gap + 30, 20, x - 30, 20, fill=ACCENT if i <= self.step else LINE, width=2)
            fill = ACCENT if (done or cur) else '#ffffff'
            c.create_oval(x - 16, 4, x + 16, 36, fill=fill, outline=ACCENT if (done or cur) else '#9a9a9a', width=2)
            c.create_text(x, 20, text=str(i + 1), fill='#ffffff' if (done or cur) else TEXT, font=('Segoe UI Semibold', 11))
            c.create_text(x, 48, text=name, fill=TEXT, font=('Segoe UI Semibold' if cur else 'Segoe UI', 10))

    def _set_step(self, i):
        self.step = i
        self._draw_steps()

    # ------------------------------------------------------------ helpers
    def _say(self, text):
        self.log.configure(state='normal')
        self.log.insert('end', '[%s]  %s\n' % (time.strftime('%H:%M:%S'), text))
        self.log.see('end')
        self.log.configure(state='disabled')

    def _set_log(self, text):
        self.log.configure(state='normal')
        self.log.delete('1.0', 'end')
        self.log.insert('end', text)
        self.log.configure(state='disabled')

    def _pick_folder(self):
        p = filedialog.askdirectory(title='Folder with damaged files')
        if p:
            self._set_source(os.path.normpath(p))

    def _pick_file(self):
        p = filedialog.askopenfilename(title='Damaged file')
        if p:
            self._set_source(os.path.normpath(p))

    def _set_source(self, p):
        self.src.set(p)
        if not self.out.get():
            base = p if os.path.isdir(p) else os.path.dirname(p)
            self.out.set(base.rstrip('\\/') + '_Repaired')

    def _pick_out(self):
        p = filedialog.askdirectory(title='Folder for repaired files')
        if p:
            self.out.set(os.path.normpath(p))

    def _open_out(self):
        p = self.out.get()
        if not os.path.isdir(p):
            return
        if os.name == 'nt':
            os.startfile(p)
        else:
            try:
                subprocess.Popen(['open' if sys.platform == 'darwin' else 'xdg-open', p])
            except OSError:
                messagebox.showinfo(APP_NAME, 'The repaired files are in:\n%s' % p)

    def _busy(self, on):
        self.b_an.configure(state='disabled' if on else 'normal')
        self.b_rep.configure(state='disabled' if on or not any(i.repairable for i in self.items) else 'normal')
        self.b_stop.configure(state='normal' if on else 'disabled')
        self.b_csv.configure(state='disabled' if on or not self.items else 'normal')

    def _row(self, it):
        if it.result:
            tag = 'ok' if it.result == 'Repaired' else 'fail' if it.result == 'Failed' else 'no'
            detail = '%s: %s' % (it.result, it.note)
        else:
            tag = 'ok' if it.repairable else 'no'
            detail = ('Can be repaired. ' if it.repairable else 'Cannot be repaired. ') + it.note
        vals = (it.rel, engine.KIND_NAMES.get(it.kind, ''),
                engine.human(it.size), '%.1f%%' % it.encrypted_pct, '%.0f%%' % it.recover_pct, detail)
        return vals, tag

    def _visible(self, it):
        f = self.flt.get()
        return f == 'All files' or (f == 'Can be repaired') == it.repairable

    def _refill(self):
        self.tree.delete(*self.tree.get_children())
        for idx, it in enumerate(self.items):
            if self._visible(it):
                vals, tag = self._row(it)
                self.tree.insert('', 'end', iid=str(idx), values=vals, tags=(tag,))

    def _totals(self):
        n = len(self.items)
        if not n:
            return
        orig = sum(i.orig_size for i in self.items) or 1
        enc = sum(i.orig_size * i.encrypted_pct / 100.0 for i in self.items)
        rec = sum(i.orig_size * i.recover_pct / 100.0 for i in self.items)
        ok = sum(1 for i in self.items if i.repairable)
        self.s_found.set('Damaged files found: %d  (%s)' % (n, engine.human(orig)))
        self.s_enc.set('Encrypted part: %.1f%% of the data' % (100.0 * enc / orig))
        self.s_rec.set('Can be repaired: %d of %d files, %.1f%% of the data' % (ok, n, 100.0 * rec / orig))
        self.s_count.set('%d files, %d can be repaired' % (n, ok))

    # ------------------------------------------------------------ analyse
    def _analyze(self):
        src = self.src.get().strip().strip('"')
        if not src or not os.path.exists(src):
            messagebox.showwarning(APP_NAME, 'Choose a folder or a file that exists.')
            return
        self.items = []
        self._refill()
        self._set_step(1)
        self.phase = 'analyze'
        self.stop_flag.clear()
        self.started = time.time()
        self.pct.set('0%')
        self.bar.configure(value=0)
        self.s_phase.set('Looking for damaged files...')
        self.status.set('Analyzing')
        self._busy(True)
        self._say('Scanning %s' % src)
        out = self.out.get().strip()
        self.worker = threading.Thread(target=self._analyze_job, args=(src, self.sub.get(), out), daemon=True)
        self.worker.start()

    def _analyze_job(self, src, sub, out):
        q = self.queue
        work = engine.make_workdir()
        try:
            paths = list(engine.scan(src, sub, out or None, self.stop_flag.is_set))
            q.put(('found', len(paths)))
            root = src if os.path.isdir(src) else os.path.dirname(src)
            done = []
            for n, p in enumerate(paths, 1):
                if self.stop_flag.is_set():
                    break
                try:
                    it = engine.analyze(engine.Item(p, root), work)
                except OSError as e:
                    q.put(('log', 'Cannot read %s (%s)' % (p, e.__class__.__name__)))
                    continue
                done.append(it)
                q.put(('item', it, n, len(paths)))
            engine.assign_jpeg_quality(done)
        except Exception as e:
            q.put(('log', 'Analysis stopped: %s' % e))
        finally:
            shutil.rmtree(work, ignore_errors=True)
            q.put(('done', 'analyze'))

    # ------------------------------------------------------------ repair
    def _repair(self):
        out = self.out.get().strip().strip('"')
        src = self.src.get().strip().strip('"')
        if not out:
            messagebox.showwarning(APP_NAME, 'Choose a folder for the repaired files.')
            return
        src_dir = src if os.path.isdir(src) else os.path.dirname(src)
        if os.path.normcase(os.path.abspath(out)) == os.path.normcase(os.path.abspath(src_dir)):
            messagebox.showwarning(APP_NAME, 'Choose a different folder, so the repaired copies are kept apart from the damaged files.')
            return
        todo = [i for i in self.items if i.repairable and i.result != 'Repaired']
        if not todo:
            messagebox.showinfo(APP_NAME, 'There is nothing to repair.')
            return
        try:
            os.makedirs(out, exist_ok=True)
            free = shutil.disk_usage(out).free
        except OSError as e:
            messagebox.showerror(APP_NAME, 'Cannot use that folder:\n%s' % e)
            return
        need = sum(i.orig_size for i in todo)
        if need > free:
            if not messagebox.askyesno(APP_NAME, 'The repaired files need about %s but only %s is free there.\n\nContinue anyway?'
                                       % (engine.human(need), engine.human(free))):
                return
        self._set_step(2)
        self.phase = 'repair'
        self.stop_flag.clear()
        self.started = time.time()
        self.pct.set('0%')
        self.bar.configure(value=0)
        self.s_phase.set('Repairing...')
        self.status.set('Repairing')
        self._busy(True)
        self._say('Repairing %d files into %s' % (len(todo), out))
        self.worker = threading.Thread(target=self._repair_job, args=(todo, out), daemon=True)
        self.worker.start()

    def _repair_job(self, todo, out):
        q = self.queue
        work = engine.make_workdir()
        total = sum(i.orig_size for i in todo) or 1
        done_bytes = 0
        try:
            for it in todo:
                if self.stop_flag.is_set():
                    break
                try:
                    ok, msg, dst = engine.repair(it, out, work)
                except Exception as e:
                    ok, msg = False, 'Error: %s' % e.__class__.__name__
                it.result = 'Repaired' if ok else 'Failed'
                it.note = msg
                done_bytes += it.orig_size
                q.put(('fixed', it, done_bytes, total))
        finally:
            shutil.rmtree(work, ignore_errors=True)
            q.put(('done', 'repair'))

    def _stop(self):
        self.stop_flag.set()
        self.s_phase.set('Stopping after the current file...')

    # ------------------------------------------------------------ results
    def _write_report(self, path):
        with open(path, 'w', newline='', encoding='utf-8-sig') as f:
            w = csv.writer(f)
            w.writerow(['File', 'Type', 'Size (bytes)', 'Encrypted %', 'Recoverable %', 'Can be repaired', 'Result', 'Details'])
            for it in self.items:
                w.writerow([it.path, engine.KIND_NAMES.get(it.kind, ''), it.size, '%.1f' % it.encrypted_pct,
                            '%.0f' % it.recover_pct, 'yes' if it.repairable else 'no', it.result, it.note])

    def _save_report(self):
        p = filedialog.asksaveasfilename(title='Save report', defaultextension='.csv', initialfile='repair_report.csv',
                                         filetypes=[('CSV file', '*.csv')])
        if p:
            try:
                self._write_report(p)
                self._say('Report saved: %s' % p)
            except OSError as e:
                messagebox.showerror(APP_NAME, 'Could not save the report:\n%s' % e)

    def _poll(self):
        try:
            for _ in range(400):
                msg = self.queue.get_nowait()
                kind = msg[0]
                if kind == 'found':
                    self._say('Found %d damaged files' % msg[1])
                    self.s_phase.set('Analyzing %d files...' % msg[1])
                    if not msg[1]:
                        self._say('No STOP/Djvu damaged files were found there.')
                elif kind == 'item':
                    it, n, total = msg[1], msg[2], msg[3]
                    self.items.append(it)
                    if self._visible(it):
                        vals, tag = self._row(it)
                        self.tree.insert('', 'end', iid=str(len(self.items) - 1), values=vals, tags=(tag,))
                    p = 100.0 * n / max(1, total)
                    self.bar.configure(value=p)
                    self.pct.set('%d%%' % p)
                    if n % 25 == 0 or n == total:
                        self._totals()
                elif kind == 'fixed':
                    it, done, total = msg[1], msg[2], msg[3]
                    idx = str(self.items.index(it))
                    if self.tree.exists(idx):
                        vals, tag = self._row(it)
                        self.tree.item(idx, values=vals, tags=(tag,))
                        self.tree.see(idx)
                    if it.result == 'Failed':
                        self._say('Failed: %s (%s)' % (it.rel, it.note))
                    p = 100.0 * done / total
                    self.bar.configure(value=p)
                    self.pct.set('%d%%' % p)
                elif kind == 'log':
                    self._say(msg[1])
                elif kind == 'done':
                    self._finished(msg[1])
        except queue.Empty:
            pass
        if self.phase in ('analyze', 'repair'):
            e = int(time.time() - self.started)
            self.s_time.set('Elapsed %02d:%02d:%02d' % (e // 3600, e % 3600 // 60, e % 60))
        self.after(120, self._poll)

    def _finished(self, what):
        stopped = self.stop_flag.is_set()
        self.phase = 'idle'
        self._totals()
        if what == 'analyze':
            ok = sum(1 for i in self.items if i.repairable)
            self.s_phase.set('Analysis stopped' if stopped else 'Analysis finished')
            self._say('Analysis %s: %d of %d files can be repaired' % ('stopped' if stopped else 'finished', ok, len(self.items)))
            self.status.set('Ready')
            if not stopped:
                self.bar.configure(value=100)
                self.pct.set('100%')
        else:
            good = sum(1 for i in self.items if i.result == 'Repaired')
            bad = sum(1 for i in self.items if i.result == 'Failed')
            self.s_phase.set('Repair stopped' if stopped else 'Repair finished')
            self._say('Repair %s: %d repaired, %d failed' % ('stopped' if stopped else 'finished', good, bad))
            out = self.out.get().strip()
            try:
                self._write_report(os.path.join(out, 'repair_report.csv'))
                self._say('Report written: %s' % os.path.join(out, 'repair_report.csv'))
            except OSError:
                pass
            self.b_open.configure(state='normal')
            self.status.set('Ready')
            self._set_step(3)
            if not stopped:
                self.bar.configure(value=100)
                self.pct.set('100%')
        self._busy(False)

    def _close(self):
        if self.phase != 'idle':
            if not messagebox.askyesno(APP_NAME, 'Work is still running. Stop and close?'):
                return
            self.stop_flag.set()
        self.destroy()


def main():
    if os.name == 'nt':
        try:
            import ctypes
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            pass
    App().mainloop()


if __name__ == '__main__':
    main()
