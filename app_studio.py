#!/usr/bin/env python3
"""
AI Vocals Studio Pro v4.0  — Maximum Effects Edition
"""
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, simpledialog
import os, json, threading, time, math, random, shutil, subprocess, sys, tempfile
from pathlib import Path
import numpy as np
import soundfile as sf
from gtts import gTTS
from pydub import AudioSegment

try:
    import librosa
    HAS_LIBROSA = True
except ImportError:
    HAS_LIBROSA = False

try:
    from svc_engine import SoVitsEngine, status_label, STATUS_READY, STATUS_UNTRAINED
    HAS_ENGINE = True
except Exception:
    HAS_ENGINE = False

# ═══════════════════════════════════════════════════════════════════
#  THEME — rich neon cyberpunk palette
# ═══════════════════════════════════════════════════════════════════
C = {
    'bg':       '#05050f',
    'bg2':      '#0a0a1e',
    'bg3':      '#0f0f28',
    'card':     '#111130',
    'card2':    '#16163c',
    'border':   '#1e1e55',
    'cyan':     '#00e5ff',
    'blue':     '#3d7eff',
    'purple':   '#bf5fff',
    'magenta':  '#ff00cc',
    'green':    '#00ffaa',
    'lime':     '#aaff00',
    'orange':   '#ff8800',
    'red':      '#ff1a4a',
    'gold':     '#ffd700',
    'white':    '#f0f4ff',
    'gray':     '#6677aa',
    'dim':      '#2a2a66',
}

FONT = {
    'h1':    ('Courier New', 26, 'bold'),
    'h2':    ('Courier New', 15, 'bold'),
    'h3':    ('Courier New', 12, 'bold'),
    'h4':    ('Courier New', 11, 'bold'),
    'body':  ('Courier New', 11),
    'sm':    ('Courier New', 10),
    'xs':    ('Courier New', 9),
    'mono':  ('Courier New', 11),
}

GLITCH_CHARS = '!@#$%^&|/\\<>?{}[]01XY'

VOICE_PERSONAS = {
    'pacaveli':          {'pitch': -4,   'speed': 1.08, 'reverb': 0.4,  'gain': 4,  'eq_low': 1.5, 'eq_mid': 0.8, 'eq_high': 0.9, 'desc': 'Pacaveli – West Coast rap, deep raw authority'},
    'pacaveli_enhanced': {'pitch': -4.5, 'speed': 1.10, 'reverb': 0.45, 'gain': 5,  'eq_low': 1.6, 'eq_mid': 0.7, 'eq_high': 0.8, 'desc': 'Pacaveli Enhanced – maximum realism'},
    'male':               {'pitch': -4,   'speed': 1.00, 'reverb': 0.20, 'gain': 2,  'eq_low': 1.3, 'eq_mid': 0.9, 'eq_high': 1.0, 'desc': 'Generic deep male voice'},
    'female':             {'pitch': 4,    'speed': 1.00, 'reverb': 0.15, 'gain': 0,  'eq_low': 0.8, 'eq_mid': 1.1, 'eq_high': 1.2, 'desc': 'Generic bright female voice'},
    'robot':              {'pitch': 0,    'speed': 0.88, 'reverb': 0.50, 'gain': 6,  'eq_low': 1.5, 'eq_mid': 0.7, 'eq_high': 0.5, 'desc': 'Vocoder / robot effect'},
    'default':            {'pitch': 0,    'speed': 1.00, 'reverb': 0.05, 'gain': 0,  'eq_low': 1.0, 'eq_mid': 1.0, 'eq_high': 1.0, 'desc': 'Clean unmodified voice'},
}

# ═══════════════════════════════════════════════════════════════════
#  COLOUR HELPERS
# ═══════════════════════════════════════════════════════════════════
def _parse(h): return int(h[1:3],16), int(h[3:5],16), int(h[5:7],16)

def blend(fg, bg_hex, a):
    fr,fg_,fb = _parse(fg)
    br,bg_v,bb = _parse(bg_hex)
    r=int(fr*a+br*(1-a)); g=int(fg_*a+bg_v*(1-a)); b=int(fb*a+bb*(1-a))
    return f'#{min(r,255):02x}{min(g,255):02x}{min(b,255):02x}'

def blen(fg, a):  return blend(fg, C['bg3'], a)

# ═══════════════════════════════════════════════════════════════════
#  SCROLLABLE FRAME
# ═══════════════════════════════════════════════════════════════════
class ScrollableFrame(tk.Frame):
    def __init__(self, parent, **kw):
        kw.setdefault('bg', C['bg'])
        super().__init__(parent, **kw)
        bg = kw['bg']
        self._cv = tk.Canvas(self, bg=bg, highlightthickness=0, bd=0)
        self._sb = tk.Scrollbar(self, orient='vertical', command=self._cv.yview,
                                bg=C['bg3'], troughcolor=C['bg2'], bd=0, width=12)
        self.inner = tk.Frame(self._cv, bg=bg)
        self._win = self._cv.create_window((0,0), window=self.inner, anchor='nw')
        self._cv.configure(yscrollcommand=self._sb.set)
        self._sb.pack(side='right', fill='y')
        self._cv.pack(side='left', fill='both', expand=True)
        self.inner.bind('<Configure>', lambda _: self._cv.configure(scrollregion=self._cv.bbox('all')))
        self._cv.bind('<Configure>', lambda e: self._cv.itemconfig(self._win, width=e.width))
        self._cv.bind('<Enter>', self._on)
        self._cv.bind('<Leave>', self._off)
        self.inner.bind('<Enter>', self._on)

    def _on(self, _=None):
        self._cv.bind_all('<MouseWheel>', self._scroll)
        self._cv.bind_all('<Button-4>', self._scroll)
        self._cv.bind_all('<Button-5>', self._scroll)

    def _off(self, _=None):
        self._cv.unbind_all('<MouseWheel>')
        self._cv.unbind_all('<Button-4>')
        self._cv.unbind_all('<Button-5>')

    def _scroll(self, e):
        if e.num == 4:   self._cv.yview_scroll(-3, 'units')
        elif e.num == 5: self._cv.yview_scroll(3, 'units')
        else:            self._cv.yview_scroll(int(-1*(e.delta/120)), 'units')

# ═══════════════════════════════════════════════════════════════════
#  ANIMATED CARD BORDER
# ═══════════════════════════════════════════════════════════════════
class AniCard(tk.Frame):
    def __init__(self, parent, accent=None, **kw):
        self._accent = accent or C['cyan']
        kw.setdefault('bg', C['card'])
        super().__init__(parent, bg=kw['bg'],
                         highlightthickness=2, highlightbackground=C['border'])
        self.inner = tk.Frame(self, bg=kw['bg'])
        self.inner.pack(fill='both', expand=True, padx=18, pady=14)
        self._ph = random.uniform(0, math.pi*2)
        self.after(1200 + random.randint(0, 600), self._tick)  # defer

    def _tick(self):
        try:
            if not self.winfo_exists(): return
        except tk.TclError: return
        self._ph += 0.035
        b = 0.12 + 0.18 * math.sin(self._ph)
        col = blen(self._accent, b)
        self.configure(highlightbackground=col)
        self.after(400, self._tick)

# ═══════════════════════════════════════════════════════════════════
#  SECTION HEADER  (canvas with pulsing dot + scanning line)
# ═══════════════════════════════════════════════════════════════════
class SectionHdr(tk.Canvas):
    def __init__(self, parent, text, color, bg=None):
        self._bg = bg or C['bg']
        super().__init__(parent, height=30, bg=self._bg, highlightthickness=0)
        self.pack(fill='x', padx=14, pady=(14, 4))
        self._text = text
        self._color = color
        self.bind('<Configure>', lambda _: self._draw())
        self._draw()

    def _draw(self):
        self.delete('all')
        w = self.winfo_width() or 900
        h = 30
        # Solid dot
        self.create_oval(4, h//2-4, 12, h//2+4,
                         fill=blen(self._color, 0.4), outline='')
        self.create_oval(5, h//2-3, 11, h//2+3, fill=self._color, outline='')
        # Text shadow + text
        tx = 24
        self.create_text(tx+1, h//2+1, text=self._text,
                         fill='#000033', font=FONT['h3'], anchor='w')
        self.create_text(tx, h//2, text=self._text,
                         fill=self._color, font=FONT['h3'], anchor='w')
        # Divider line
        lx = tx + len(self._text)*8 + 14
        self.create_line(lx, h//2, w-6, h//2,
                         fill=blen(self._color, 0.25), width=1)

# ═══════════════════════════════════════════════════════════════════
#  NEON BUTTON — shimmer + ripple + deep glow
# ═══════════════════════════════════════════════════════════════════
class NeonBtn(tk.Canvas):
    def __init__(self, parent, text, cmd=None, color=None,
                 w=180, h=44, font=None, **kw):
        color = color or C['cyan']
        kw.setdefault('bg', parent.cget('bg') if hasattr(parent,'cget') else C['card'])
        super().__init__(parent, width=w, height=h,
                         highlightthickness=0, bd=0, **kw)
        self.text, self.cmd, self.color = text, cmd, color
        self.W, self.H = w, h
        self.font = font or FONT['h4']
        self._hover = False
        self._ph = 0.0
        self._scan_x = w + 20       # scan shimmer pos
        self._rip_r = 0             # ripple radius
        self._rip_a = 0.0           # ripple alpha
        self._draw()
        self.bind('<Enter>',    self._enter)
        self.bind('<Leave>',    self._leave)
        self.bind('<Button-1>', self._click)
        self.after(1000 + random.randint(0, 800), self._tick)  # defer

    # ── helpers ──────────────────────────────────────────────
    def _rrect(self, x1,y1,x2,y2,r, **kw):
        p=[x1+r,y1, x2-r,y1, x2,y1, x2,y1+r,
           x2,y2-r, x2,y2, x2-r,y2, x1+r,y2,
           x1,y2, x1,y2-r, x1,y1+r, x1,y1]
        return self.create_polygon(p, smooth=True, **kw)

    def _hex2rgb(self, h):
        return int(h[1:3],16), int(h[3:5],16), int(h[5:7],16)

    def _bl(self, h, a, bg='#05050f'):
        fr,fg_,fb = self._hex2rgb(h)
        br,bg_v,bb = self._hex2rgb(bg)
        return f'#{int(fr*a+br*(1-a)):02x}{int(fg_*a+bg_v*(1-a)):02x}{int(fb*a+bb*(1-a)):02x}'

    # ── draw ─────────────────────────────────────────────────
    def _draw(self):
        self.delete('all')
        w, h, r = self.W, self.H, 10
        pulse = 0.5 + 0.5*math.sin(self._ph) if self._hover else 0.0

        # Outer aura (multiple layers)
        if self._hover:
            for i in range(10, 0, -1):
                a = pulse * 0.28 / i
                c = self._bl(self.color, a)
                self._rrect(i*1.8, i*1.8, w-i*1.8, h-i*1.8, r+2, fill=c, outline='')

        # Body fill
        body_a = 0.16 if self._hover else 0.07
        body = self._bl(self.color, body_a, C['card'])
        self._rrect(2,2,w-2,h-2, r, fill=body, outline=self.color, width=1+(self._hover))

        # Inner top shine
        if self._hover:
            shine_a = 0.12 + 0.10*pulse
            sc = self._bl('#ffffff', shine_a)
            self.create_line(14, 5, w-14, 5, fill=sc, width=1)
            self.create_line(14, 6, w-14, 6, fill=self._bl('#ffffff', shine_a*0.4))

        # Scan shimmer (vertical bright line sweeping L→R on hover)
        if self._hover and 0 <= self._scan_x <= w:
            for i in range(6, 0, -1):
                sx = self._scan_x
                a = 0.55 * (1 - i/7)
                sc = self._bl('#ffffff', a)
                if 0 <= sx-i < w:
                    self.create_line(sx-i, 4, sx-i, h-4, fill=sc)

        # Text shadow + text
        tc = C['white'] if self._hover else self.color
        for dx,dy in [(2,2),(1,1)]:
            self.create_text(w//2+dx, h//2+dy, text=self.text,
                             fill='#000000', font=self.font, anchor='center')
        self.create_text(w//2, h//2, text=self.text,
                         fill=tc, font=self.font, anchor='center')

        # Ripple effect
        if self._rip_r > 0 and self._rip_a > 0.02:
            cx, cy = w//2, h//2
            rc = self._bl(self.color, self._rip_a)
            r2 = int(self._rip_r)
            self.create_oval(cx-r2, cy-r2, cx+r2, cy+r2,
                             fill='', outline=rc, width=2)

    def _enter(self, _=None):
        self._hover = True
        self._scan_x = -10
        self._draw()

    def _leave(self, _=None):
        self._hover = False
        self._draw()

    def _click(self, _=None):
        self._rip_r = 4
        self._rip_a = 0.75
        if self.cmd: self.cmd()

    def _tick(self):
        try:
            if not self.winfo_exists(): return
        except tk.TclError: return
        changed = False
        if self._hover:
            self._ph += 0.14
            if self._scan_x < self.W + 20:
                self._scan_x += 8
            changed = True
        if self._rip_r > 0:
            self._rip_r += 7
            self._rip_a *= 0.72
            if self._rip_a < 0.02: self._rip_r = 0
            changed = True
        if changed: self._draw()
        # idle: check every 600ms; active: animate at 80ms
        self.after(80 if changed else 600, self._tick)

# ═══════════════════════════════════════════════════════════════════
#  NEON PROGRESS BAR  (taller, more dramatic)
# ═══════════════════════════════════════════════════════════════════
class NeonBar(tk.Canvas):
    def __init__(self, parent, w=420, h=14, color=None, **kw):
        color = color or C['cyan']
        kw.setdefault('bg', C['bg2'])
        super().__init__(parent, width=w, height=h,
                         highlightthickness=0, bd=0, **kw)
        self.W, self.H, self.color = w, h, color
        self.value = 0
        self._sh = 0
        self._draw()
        self.after(900 + random.randint(0, 400), self._tick)  # defer

    def set(self, v):
        self.value = max(0, min(100, v))
        self._draw()

    def _rrect(self, x1,y1,x2,y2,r, **kw):
        if x2-x1 < r*2: r = max(1,(x2-x1)//2)
        p=[x1+r,y1, x2-r,y1, x2,y1, x2,y1+r,
           x2,y2-r, x2,y2, x2-r,y2, x1+r,y2,
           x1,y2, x1,y2-r, x1,y1+r, x1,y1]
        return self.create_polygon(p, smooth=True, **kw)

    def _draw(self):
        self.delete('all')
        w,h = self.W, self.H
        r = h//2
        # track
        self._rrect(0,0,w,h,r, fill=C['bg3'], outline=C['dim'])
        fw = max(0, int(w*self.value/100))
        if fw > r*2:
            self._rrect(0,0,fw,h,r, fill=blen(self.color, 0.3), outline='')
            self._rrect(0,0,fw,h,r, fill=self.color, outline='')
            # shimmer
            sx = self._sh % fw
            sw = min(50, fw)
            if sx+sw < fw:
                self.create_rectangle(sx, 2, sx+sw, h-2,
                                      fill='white', outline='', stipple='gray25')
            # tip glow (multi layer)
            for gr in range(h+4, 0, -3):
                a = 0.15 * (1 - gr/(h+4))
                self.create_oval(fw-gr, -gr//2, fw+gr, h+gr//2,
                                 fill=blen(self.color, a), outline='')
            self.create_oval(fw-r, 0, fw+r, h, fill=self.color, outline='')
            self.create_oval(fw-r//2, h//4, fw+r//2, h*3//4, fill='white', outline='')

    def _tick(self):
        try:
            if not self.winfo_exists(): return
        except tk.TclError: return
        if 0 < self.value < 100:
            self._sh += 5
            self._draw()
        self.after(150, self._tick)

# ═══════════════════════════════════════════════════════════════════
#  WAVEFORM  (reflection + glow gradient + richer color)
# ═══════════════════════════════════════════════════════════════════
class Waveform(tk.Canvas):
    def __init__(self, parent, w=640, h=110, **kw):
        kw.setdefault('bg', C['bg3'])
        super().__init__(parent, width=w, height=h,
                         highlightthickness=1, highlightbackground=C['border'], **kw)
        self.W, self.H = w, h
        self._bars = []
        self._ph = 0.0
        self._bph = 0.0
        self._active = False
        self._idle()
        self.after(800 + random.randint(0, 400), self._tick)  # defer

    def _idle(self):
        self.delete('all')
        mid = int(self.H*0.58)
        self.create_line(8, mid, self.W-8, mid, fill=C['dim'], width=1, dash=(4,6))
        self.create_text(self.W//2, mid-16, text='◈  NO AUDIO  ◈',
                         fill=C['dim'], font=FONT['sm'])

    def load(self, path):
        # Run audio decoding in background — librosa can take 30s on large files
        threading.Thread(target=self._load_bg, args=(str(path),), daemon=True).start()

    def _load_bg(self, path):
        try:
            if HAS_LIBROSA:
                y, _ = librosa.load(path, sr=None, mono=True, duration=8)
                n=90; cs=max(1,len(y)//n)
                bars=[float(abs(y[i*cs:(i+1)*cs]).max()) for i in range(n)]
                mx=max(bars) or 1
                bars=[b/mx for b in bars]
            else:
                bars=[abs(math.sin(i*0.3))*0.6+random.uniform(0.1,0.4) for i in range(90)]
            self._bars = bars
            self.after(0, self._render)
        except Exception:
            self.after(0, self._idle)

    def set_active(self, v):
        self._active = v
        if not v:
            self.configure(highlightbackground=C['border'])
            if self._bars: self._render()
            else: self._idle()

    def _render(self):
        self.delete('all')
        if not self._bars: self._idle(); return
        w,h,n = self.W, self.H, len(self._bars)
        bw = w/n
        mid = int(h*0.56)   # main bars above, reflection below

        for i,bar in enumerate(self._bars):
            x = i*bw
            pulse = (1+0.32*math.sin(self._ph+i*0.24)) if self._active else 1.0
            bh = max(2, bar*(mid-6)*pulse)
            t = i/n
            # cyan → purple → magenta gradient
            if t < 0.5:
                t2=t*2
                r=int(0+155*t2); g=int(229-136*t2); b=255
            else:
                t2=(t-0.5)*2
                r=int(155+100*t2); g=int(93-93*t2); b=int(255-55*t2)
            col = f'#{min(r,255):02x}{min(g,255):02x}{min(b,255):02x}'

            # glow pool beneath bar
            for gd in range(5,0,-1):
                a=0.06*(1-gd/6)
                gc=blen(col, a)
                self.create_rectangle(x, mid, x+bw, mid+gd*4, fill=gc, outline='')

            # main bar
            self.create_rectangle(x+1, mid-bh, x+bw-1, mid, fill=col, outline='')

            # top cap glow
            cr,cg,cb=int(r*1.0),int(g*1.0),int(b*1.0)
            cap=f'#{min(cr+80,255):02x}{min(cg+80,255):02x}{min(cb+80,255):02x}'
            self.create_rectangle(x+1, mid-bh, x+bw-1, mid-bh+2, fill=cap, outline='')

            # reflection
            ref_h = bh*0.38
            if ref_h > 1:
                fr=int(r*0.28); fg_=int(g*0.28); fb=int(b*0.28)
                rc=f'#{fr:02x}{fg_:02x}{fb:02x}'
                self.create_rectangle(x+1, mid+1, x+bw-1, mid+ref_h, fill=rc, outline='')

        # center line
        self.create_line(0, mid, w, mid, fill=blen(C['cyan'],0.2), width=1)

        # border glow when active
        if self._active:
            bp = 0.4+0.4*math.sin(self._bph)
            self.configure(highlightbackground=blen(C['cyan'], 0.3+0.4*bp))

    def _tick(self):
        try:
            if not self.winfo_exists(): return
        except tk.TclError: return
        if self._active:
            self._ph  += 0.06
            self._bph += 0.08
            self._render()
        self.after(100 if self._active else 600, self._tick)

# ═══════════════════════════════════════════════════════════════════
#  VU METER  (taller + segment glow)
# ═══════════════════════════════════════════════════════════════════
class VU(tk.Canvas):
    def __init__(self, parent, w=280, h=22, **kw):
        kw.setdefault('bg', C['bg2'])
        super().__init__(parent, width=w, height=h,
                         highlightthickness=0, **kw)
        self.W, self.H = w, h
        self._lv=0.0; self._pk=0.0; self._ph=0
        self._draw()
        self.after(700 + random.randint(0, 300), self._tick)  # defer

    def push(self, v):
        self._lv=min(1.0,max(0,v))
        if self._lv>self._pk:
            self._pk=self._lv; self._ph=30

    def _draw(self):
        self.delete('all')
        n=32; bw=self.W/n
        for i in range(n):
            t=i/n
            on  = C['green'] if t<0.6 else (C['orange'] if t<0.85 else C['red'])
            off = '#002211' if t<0.6 else ('#221100' if t<0.85 else '#220011')
            peak= abs(self._pk-t)<(1/n) and self._ph>0
            fill= 'white' if peak else (on if self._lv>t else off)
            x=i*bw
            self.create_rectangle(x+1, 2, x+bw-1, self.H-2, fill=fill, outline='')
            # active segment glow
            if self._lv>t and not peak:
                self.create_rectangle(x+1, 2, x+bw-1, 5,
                                      fill=blen(on,0.6), outline='')

    def _tick(self):
        try:
            if not self.winfo_exists(): return
        except tk.TclError: return
        prev = self._lv
        self._lv *= 0.86
        if self._ph > 0:
            self._ph -= 1
            if self._ph == 0: self._pk = 0
        active = prev > 0.002 or self._ph > 0
        if active:
            self._draw()
        self.after(120 if active else 500, self._tick)

# ═══════════════════════════════════════════════════════════════════
#  LAYOUT HELPERS
# ═══════════════════════════════════════════════════════════════════
def mk_card(parent, accent=None):
    c = AniCard(parent, accent=accent)
    c.pack(fill='x', padx=14, pady=5)
    return c.inner

def lbl(parent, text, color=None, font=None, **pk):
    w = tk.Label(parent, text=text, fg=color or C['gray'],
                 bg=parent.cget('bg'), font=font or FONT['sm'])
    if pk: w.pack(**pk)
    return w

def entry(parent, var, width=44):
    e = tk.Entry(parent, textvariable=var, bg=C['bg3'], fg=C['white'],
                 insertbackground=C['cyan'], font=FONT['body'], relief='flat',
                 highlightthickness=1, highlightcolor=C['cyan'],
                 highlightbackground=C['border'], width=width)
    e.pack(side='left', fill='x', expand=True, ipady=7)
    return e

def textbox(parent, height=6, color=None):
    wrap = tk.Frame(parent, bg=parent.cget('bg'))
    wrap.pack(fill='x')
    t = tk.Text(wrap, height=height, wrap='word',
                bg=C['bg3'], fg=color or C['white'],
                insertbackground=C['cyan'], font=FONT['mono'], relief='flat',
                padx=12, pady=10, highlightthickness=1,
                highlightcolor=C['border'], highlightbackground=C['border'])
    sb = tk.Scrollbar(wrap, orient='vertical', command=t.yview,
                      bg=C['bg3'], troughcolor=C['bg2'], bd=0, width=10)
    t.configure(yscrollcommand=sb.set)
    t.pack(side='left', fill='both', expand=True)
    sb.pack(side='right', fill='y')
    return t

def combo(parent, var, values, width=22):
    cb = ttk.Combobox(parent, textvariable=var, values=values,
                      state='readonly', width=width, font=FONT['sm'])
    cb.pack(side='left', padx=(0,12))
    return cb

# ═══════════════════════════════════════════════════════════════════
#  MAIN APPLICATION
# ═══════════════════════════════════════════════════════════════════
class StudioPro:
    def __init__(self, root):
        self.root = root
        self.root.title("AI VOCALS STUDIO PRO  v4.0")
        self.root.geometry("1300x720")
        self.root.minsize(900, 600)
        self.root.configure(bg=C['bg'])

        # dirs
        self.MODELS  = Path('models')
        self.DATASET = Path('dataset')
        self.OUTPUT  = Path('output')
        self.INPUT   = Path('input')
        for d in [self.MODELS, self.DATASET, self.OUTPUT, self.INPUT]:
            d.mkdir(exist_ok=True)

        # state
        self.audio_path_var  = tk.StringVar()
        self.model_var       = tk.StringVar()
        self.input_type_var  = tk.StringVar(value='text')
        self.tts_voice_var    = tk.StringVar(value='default')
        self.tts_speed_var    = tk.StringVar(value='1.0')
        self._mood_var        = tk.StringVar(value='default')
        self._custom_ref_path: str | None = None
        self.train_model_var = tk.StringVar()
        self.status_var      = tk.StringVar(value='SYSTEM READY')
        self.last_output     = None
        self._generating     = False
        self._preview_proc   = None
        self._hdr_ph         = 0.0
        self._train_stop     = threading.Event()
        self._engine = SoVitsEngine(self.MODELS, self.DATASET) if HAS_ENGINE else None
        # RVC v2 engine — lazy, no import at startup
        from rvc_engine import RvcEngine
        self._rvc_engine = RvcEngine(self.MODELS)
        self._glitch_text    = None
        self._particles      = self._init_particles()
        self._matrix_cols    = self._init_matrix()

        self._setup_ttk()
        self._build_header()
        self._build_nav()
        self._content = tk.Frame(self.root, bg=C['bg'])
        self._content.pack(fill='both', expand=True)
        self._pages = {}
        self._build_generate()
        self._build_models()
        self._build_training()
        self._build_outputs()
        self._build_footer()
        self._show('generate')
        self.root.after(600,  self._refresh_models)
        self.root.after(3000, self._hdr_tick)   # defer header anim until window maps
        self.root.after(random.randint(5000,9000), self._trigger_glitch)
        
        # cleanup on close
        self.root.protocol('WM_DELETE_WINDOW', self._on_close)

    def _on_close(self):
        """Cleanup resources before closing."""
        if self._cloud_status_timer:
            self.root.after_cancel(self._cloud_status_timer)
        self.root.destroy()

    # ─── TTK STYLE ────────────────────────────────────────────────
    def _setup_ttk(self):
        s = ttk.Style(self.root)
        s.theme_use('clam')
        s.configure('TCombobox', fieldbackground=C['bg3'], background=C['bg3'],
                    foreground=C['white'], selectbackground=C['purple'],
                    selectforeground=C['white'], bordercolor=C['border'],
                    arrowcolor=C['cyan'])
        s.map('TCombobox', fieldbackground=[('readonly',C['bg3'])],
              foreground=[('readonly',C['white'])])
        s.configure('TScrollbar', background=C['bg3'], troughcolor=C['bg2'],
                    arrowcolor=C['gray'], bordercolor=C['border'])

    # ─── PARTICLES ────────────────────────────────────────────────
    def _init_particles(self):
        return [{'x': random.uniform(0,1366), 'y': random.uniform(0,120),
                 'vx': random.uniform(-0.4,0.4), 'vy': random.uniform(-0.3,0.3),
                 'r': random.uniform(1,3),
                 'color': random.choice([C['cyan'],C['purple'],C['green'],C['magenta']]),
                 'a': random.uniform(0.15,0.7),
                 'va': random.uniform(-0.005,0.005)}
                for _ in range(8)]

    def _init_matrix(self):
        return [{'x': random.randint(0,1366), 'y': random.uniform(0,120),
                 'speed': random.uniform(0.8,2.5),
                 'chars': [random.choice('0123456789ABCDEF') for _ in range(3)],
                 'alpha': random.uniform(0.1,0.35)}
                for _ in range(3)]

    # ─── HEADER ───────────────────────────────────────────────────
    def _build_header(self):
        self._hcv = tk.Canvas(self.root, height=120, bg=C['bg'],
                               highlightthickness=0)
        self._hcv.pack(fill='x')

    def _hdr_tick(self):
        try:
            if not self.root.winfo_exists(): return
        except tk.TclError: return
        self._hdr_ph += 0.055
        self._draw_header()
        self.root.after(500, self._hdr_tick)

    def _trigger_glitch(self):
        self._glitch_text = True
        self.root.after(random.randint(4500, 9000), self._trigger_glitch)

    def _draw_header(self):
        cv = self._hcv
        cv.delete('all')
        w = cv.winfo_width() or 1300
        h = 120
        ph = self._hdr_ph

        # ── gradient bg (10 bands — fast) ──
        BANDS = 10
        for i in range(BANDS):
            y1 = i * h // BANDS
            y2 = (i + 1) * h // BANDS
            t = (i + 0.5) / BANDS
            rv = int(5 + t*18); gv = int(5 + t*5); bv = int(15 + t*30)
            cv.create_rectangle(0, y1, w, y2,
                                fill=f'#{rv:02x}{gv:02x}{bv:02x}', outline='')

        # ── matrix columns (6 cols, sparse) ──
        for mc in self._matrix_cols:
            mc['y'] = (mc['y'] + mc['speed']) % (h + 30)
            x = mc['x'] % w
            for j, ch in enumerate(mc['chars']):
                y_ = mc['y'] - j * 14
                if 0 <= y_ <= h:
                    a = mc['alpha'] * (1 - j / len(mc['chars']))
                    cv.create_text(x, y_, text=ch,
                                   fill=blen(C['green'], a),
                                   font=('Courier New', 9, 'bold'), anchor='center')

        # ── 1 wave layer (step=10 — fewer points) ──
        pts = []
        for x in range(0, w + 2, 10):
            wave = math.sin(x / w * 12 * math.pi + ph) * 4
            pts.extend([x, h - 6 + wave])
        if len(pts) >= 4:
            cv.create_line(pts, fill=blen(C['cyan'], 0.40), width=2, smooth=True)

        # ── particles (15) ──
        for p in self._particles:
            p['x'] = (p['x'] + p['vx']) % w
            p['y'] = (p['y'] + p['vy']) % h
            p['a'] = max(0.05, min(0.8, p['a'] + p['va']))
            r = p['r']
            cv.create_oval(p['x']-r, p['y']-r, p['x']+r, p['y']+r,
                           fill=blen(p['color'], p['a']), outline='')

        # ── scan line (single) ──
        scan_y = int((ph * 18) % h)
        cv.create_line(0, scan_y, w, scan_y, fill=blen(C['cyan'], 0.25), width=1)

        # ── title shadows + text ──
        title = self._glitch_text and self._make_glitch('🎤  AI VOCALS STUDIO PRO') \
                or '🎤  AI VOCALS STUDIO PRO'
        if self._glitch_text:
            self._glitch_text = None  # show one frame then done

        cy = 64
        for dx,dy,col,a in [(4,4,C['purple'],0.5),(2,2,C['cyan'],0.3),(1,1,C['white'],0.1)]:
            cv.create_text(w//2+dx, cy+dy, text=title,
                           fill=blen(col, a), font=FONT['h1'], anchor='center')
        cv.create_text(w//2, cy, text=title,
                       fill=C['cyan'], font=FONT['h1'], anchor='center')

        # subtitle
        cv.create_text(w//2, cy+36,
                       text='PROFESSIONAL  VOICE  SYNTHESIS  ENGINE  v4.0',
                       fill=blen(C['purple'], 0.9), font=FONT['sm'], anchor='center')

        # ── corner brackets ──
        self._corner_brackets(cv, w, h)

        # ── hex readout ──
        hx = f'{int(ph*1000) & 0xFFFF:04X}'
        cv.create_text(w-16, 14, text=f'[{hx}]',
                       fill=blen(C['green'], 0.4), font=FONT['xs'], anchor='ne')

    def _make_glitch(self, text):
        out = ''
        for c in text:
            if c not in (' ','🎤') and random.random() < 0.22:
                out += random.choice(GLITCH_CHARS)
            else:
                out += c
        return out

    def _corner_brackets(self, cv, w, h):
        s, t = 22, 2
        for (x1,y1,x2,y2), col in [
            ((0,0,s,s), C['cyan']),
            ((w-s,0,w,s), C['purple']),
            ((0,h-s,s,h), C['green']),
            ((w-s,h-s,w,h), C['magenta']),
        ]:
            # horizontal
            cv.create_line(x1,y1,x1+s,y1, fill=col, width=t)
            cv.create_line(x2-s,y2,x2,y2, fill=col, width=t)
            # vertical
            cv.create_line(x1,y1,x1,y1+s, fill=col, width=t)
            cv.create_line(x2,y2-s,x2,y2, fill=col, width=t)
            # corner dot
            cv.create_oval(x1-2,y1-2,x1+2,y1+2, fill=col, outline='')
            cv.create_oval(x2-2,y2-2,x2+2,y2+2, fill=col, outline='')

    # ─── NAV BAR ──────────────────────────────────────────────────
    def _build_nav(self):
        nav = tk.Frame(self.root, bg=C['bg2'], height=54)
        nav.pack(fill='x')
        nav.pack_propagate(False)
        tk.Canvas(nav, height=1, bg=C['border'], highlightthickness=0).pack(fill='x')
        center = tk.Frame(nav, bg=C['bg2'])
        center.pack(expand=True, fill='both')
        self._nav_btns = {}
        self._cur_page = 'generate'
        tabs = [
            ('generate','⚡  GENERATE', C['cyan']),
            ('models',  '🤖  MODELS',   C['purple']),
            ('training','🎓  TRAINING',  C['green']),
            ('outputs', '📁  OUTPUTS',   C['orange']),
        ]
        for key,lbl_,color in tabs:
            b = tk.Label(center, text=lbl_, font=FONT['h4'],
                         fg=C['dim'], bg=C['bg2'], padx=26, pady=12, cursor='hand2')
            b.pack(side='left')
            b.bind('<Button-1>', lambda e,k=key: self._show(k))
            b.bind('<Enter>',    lambda e,b_=b,c=color: b_.config(fg=c))
            b.bind('<Leave>',    lambda e,b_=b,k=key:
                   b_.config(fg=C['white'] if self._cur_page==k else C['dim']))
            self._nav_btns[key] = (b, color)
        tk.Canvas(nav, height=1, bg=C['border'], highlightthickness=0).pack(fill='x',side='bottom')

    def _show(self, key):
        for f in self._pages.values(): f.pack_forget()
        self._pages[key].pack(fill='both', expand=True)
        self._cur_page = key
        for k,(b,col) in self._nav_btns.items():
            b.config(fg=col if k==key else C['dim'])

    # ═══════════════════════════════════════════════════════════════
    #  PAGE: GENERATE
    # ═══════════════════════════════════════════════════════════════
    def _build_generate(self):
        sf_ = ScrollableFrame(self._content)
        self._pages['generate'] = sf_
        f = sf_.inner

        SectionHdr(f, 'INPUT SOURCE', C['cyan'])
        c = mk_card(f, C['cyan'])
        rb = tk.Frame(c, bg=C['card2'])
        rb.pack(fill='x', pady=6)
        for val,txt in [('text','📝   TEXT TO SPEECH'),('audio','🎵   AUDIO TO AUDIO')]:
            tk.Radiobutton(rb, text=txt, variable=self.input_type_var,
                           value=val, command=self._toggle_input,
                           fg=C['cyan'], bg=C['card2'], selectcolor=C['bg3'],
                           activeforeground=C['white'], activebackground=C['card2'],
                           font=FONT['body']).pack(side='left', padx=20, pady=6)

        # input container
        self._inp_host = tk.Frame(f, bg=C['bg'])
        self._inp_host.pack(fill='x')

        # text section
        self._txt_sec = tk.Frame(self._inp_host, bg=C['bg'])
        SectionHdr(self._txt_sec, 'TEXT INPUT', C['cyan'])
        tc = mk_card(self._txt_sec, C['cyan'])
        self._text_box = textbox(tc, height=6)
        self._text_box.insert('1.0','Enter lyrics or speech text here...')
        self._text_box.bind('<FocusIn>', self._clr_ph)
        tr = tk.Frame(tc, bg=C['card2'])
        tr.pack(fill='x', pady=6)
        lbl(tr,'MOOD:', side='left', padx=(0,8))
        for _mk, _ml in [('default','🎤 Default'), ('aggressive','😤 Aggressive'),
                          ('storytelling','📖 Story'), ('emotional','💔 Emotional')]:
            tk.Radiobutton(tr, text=_ml, variable=self._mood_var, value=_mk,
                           fg=C['cyan'], bg=C['card2'], selectcolor=C['bg3'],
                           activeforeground=C['white'], activebackground=C['card2'],
                           font=FONT['sm']).pack(side='left', padx=6, pady=4)
        NeonBtn(tr,'📎 Custom…', cmd=self._pick_custom_ref,
                color=C['dim'], w=110, h=32).pack(side='left', padx=(8,0))
        lbl(tr,'SPEED:', side='left', padx=(12,8))
        combo(tr, self.tts_speed_var, ['0.6','0.8','0.9','1.0','1.1','1.2','1.5'], 10)

        # audio section
        self._aud_sec = tk.Frame(self._inp_host, bg=C['bg'])
        SectionHdr(self._aud_sec, 'AUDIO INPUT', C['cyan'])
        ac = mk_card(self._aud_sec, C['cyan'])
        ar = tk.Frame(ac, bg=C['card2'])
        ar.pack(fill='x', pady=6)
        entry(ar, self.audio_path_var, width=46)
        NeonBtn(ar,'BROWSE',cmd=self._sel_audio, color=C['cyan'],w=115,h=38).pack(side='right',padx=(10,0))
        NeonBtn(ar,'⚡ REPLACE SONG VOCALS',cmd=self._replace_song,
            color=C['green'],w=220,h=38).pack(side='right',padx=(10,0))
        self._audio_wave = Waveform(ac, w=640, h=90)
        self._audio_wave.pack(fill='x', pady=8)

        # model selection
        SectionHdr(f,'VOICE MODEL', C['purple'])
        mc_ = mk_card(f, C['purple'])
        mr = tk.Frame(mc_, bg=C['card2'])
        mr.pack(fill='x', pady=6)
        lbl(mr,'MODEL:', side='left', padx=(0,10))
        self._gen_cb = combo(mr, self.model_var, [], 28)
        self._gen_cb.bind('<<ComboboxSelected>>', self._on_model_sel)
        NeonBtn(mr,'▶  PREVIEW', cmd=self._preview_model, color=C['green'],  w=140,h=38).pack(side='left',padx=(0,8))
        NeonBtn(mr,'■  STOP',    cmd=self._stop_preview,  color=C['red'],    w=95, h=38).pack(side='left')
        self._model_info = lbl(mc_,'Select a model to see info', color=C['gray'])
        self._model_info.pack(anchor='w', pady=(6,0))
        self._prev_wave = Waveform(mc_, w=640, h=70)
        self._prev_wave.pack(fill='x', pady=8)

        # FX
        SectionHdr(f,'VOICE EFFECTS', C['orange'])
        fx = mk_card(f, C['orange'])
        _er = tk.Frame(fx, bg=C['card2'])
        _er.pack(anchor='w', pady=(0,4), fill='x')
        self._engine_badge = tk.Label(_er, text='ENGINE: 🔄 Detecting…',
                                      fg=C['gray'], bg=C['card2'], font=FONT['sm'])
        self._engine_badge.pack(side='left')
        NeonBtn(_er, '🔑 EL Key', cmd=self._setup_el_key,
                color=C['gold'], w=100, h=28).pack(side='left', padx=(14,0))
        fxg = tk.Frame(fx, bg=C['card2'])
        fxg.pack(fill='x', pady=8)
        self._fx = {}
        for i,(lbl_t,key,lo,hi,df) in enumerate([
            ('PITCH',  'pitch', -12, 12,  0),
            ('SPEED',  'speed', 0.4, 2.0, 1.0),
            ('REVERB', 'reverb',0,   1,   0.05),
            ('BASS',   'bass',  0.4, 3.0, 1.0),
        ]):
            col_ = tk.Frame(fxg, bg=C['card2'])
            col_.grid(row=0, column=i, padx=22, pady=6, sticky='n')
            lbl(col_, lbl_t, color=C['orange']).pack()
            var = tk.DoubleVar(value=df)
            self._fx[key] = var
            tk.Scale(col_, variable=var, from_=lo, to=hi,
                     resolution=0.1 if key!='pitch' else 0.5,
                     orient='vertical', length=110,
                     bg=C['card2'], fg=C['gray'], troughcolor=C['bg3'],
                     activebackground=C['cyan'], highlightthickness=0,
                     font=FONT['xs'], width=14).pack()

        # Generate controls
        SectionHdr(f,'GENERATE', C['green'])
        gc_ = mk_card(f, C['green'])
        gr = tk.Frame(gc_, bg=C['card2'])
        gr.pack(pady=12)
        NeonBtn(gr,'⚡   GENERATE VOCALS',cmd=self._generate,
                color=C['green'],w=280,h=58,font=FONT['h2']).pack(side='left',padx=12)
        NeonBtn(gr,'🎤  CLONE OVER BEAT',cmd=self._generate_over_beat,
            color=C['cyan'],w=220,h=58,font=FONT['h3']).pack(side='left',padx=12)
        NeonBtn(gr,'⚡  QUICK CLONE + BEAT',cmd=self._quick_clone_over_beat,
            color=C['gold'],w=235,h=58,font=FONT['h3']).pack(side='left',padx=12)
        NeonBtn(gr,'🔄  CLEAR LOG',cmd=lambda:self._out_log.delete('1.0','end'),
                color=C['dim'],w=150,h=58).pack(side='left')

        # Output
        SectionHdr(f,'OUTPUT', C['purple'])
        oc_ = mk_card(f, C['purple'])
        self._out_wave = Waveform(oc_, w=640, h=90)
        self._out_wave.pack(fill='x', pady=(0,8))
        vr = tk.Frame(oc_, bg=C['card2'])
        vr.pack(fill='x', pady=(0,8))
        self._vu = VU(vr, w=300, h=22)
        self._vu.pack(side='left')
        self._out_lbl = lbl(vr,'No output yet', color=C['gray'])
        self._out_lbl.pack(side='right')
        self._out_log = textbox(oc_, height=14, color=C['green'])
        obr = tk.Frame(oc_, bg=C['card2'])
        obr.pack(fill='x', pady=10)
        NeonBtn(obr,'▶  PLAY OUTPUT',  cmd=self._play_output,     color=C['green'],  w=170,h=40).pack(side='left',padx=(0,10))
        NeonBtn(obr,'📁  OPEN FOLDER', cmd=self._open_out_folder, color=C['cyan'],   w=170,h=40).pack(side='left')

        self._toggle_input()

    # ═══════════════════════════════════════════════════════════════
    #  PAGE: MODELS
    # ═══════════════════════════════════════════════════════════════
    def _build_models(self):
        sf_ = ScrollableFrame(self._content)
        self._pages['models'] = sf_
        f = sf_.inner

        SectionHdr(f,'MODEL LIBRARY', C['purple'])
        cc = mk_card(f, C['purple'])
        cr = tk.Frame(cc, bg=C['card2'])
        cr.pack(fill='x', pady=8)
        NeonBtn(cr,'🔄  REFRESH',      cmd=self._refresh_models,    color=C['purple'],  w=150,h=42).pack(side='left',padx=(0,10))
        NeonBtn(cr,'📥  IMPORT .PTH',  cmd=self._import_model_file, color=C['orange'],  w=165,h=42).pack(side='left',padx=(0,10))
        NeonBtn(cr,'📂  IMPORT FOLDER',cmd=self._import_model_folder,color=C['orange'], w=185,h=42).pack(side='left',padx=(0,10))
        NeonBtn(cr,'🎤  CREATE VOICE', cmd=self._create_voice_profile, color=C['green'], w=175,h=42).pack(side='left',padx=(0,10))
        NeonBtn(cr,'📁  OPEN DIR',     cmd=lambda:self._open_dir(self.MODELS), color=C['dim'], w=140,h=42).pack(side='left')

        self._model_cards_host = tk.Frame(f, bg=C['bg'])
        self._model_cards_host.pack(fill='x')

    # ═══════════════════════════════════════════════════════════════
    #  PAGE: TRAINING
    # ═══════════════════════════════════════════════════════════════
    def _build_training(self):
        sf_ = ScrollableFrame(self._content)
        self._pages['training'] = sf_
        f = sf_.inner

        SectionHdr(f,'TRAINING DATA MANAGER', C['green'])
        sc = mk_card(f, C['green'])
        sr = tk.Frame(sc, bg=C['card2'])
        sr.pack(fill='x', pady=8)
        lbl(sr,'TARGET MODEL:', side='left', padx=(0,10))
        self._train_cb = combo(sr, self.train_model_var, [], 24)
        self._train_cb.bind('<<ComboboxSelected>>', lambda _: self._refresh_ds())
        NeonBtn(sr,'+ NEW MODEL', cmd=self._new_model_dlg, color=C['green'],w=150,h=38).pack(side='left')

        SectionHdr(f,'IMPORT AUDIO', C['cyan'])
        ic = mk_card(f, C['cyan'])
        ir = tk.Frame(ic, bg=C['card2'])
        ir.pack(fill='x', pady=8)
        NeonBtn(ir,'🎵  CLIP → VOCALS', cmd=self._import_clip,       color=C['cyan'],  w=170,h=40).pack(side='left',padx=(0,10))
        NeonBtn(ir,'📂  FOLDER → VOCALS',cmd=self._import_ds_folder,  color=C['cyan'],  w=190,h=40).pack(side='left',padx=(0,10))
        NeonBtn(ir,'📁  OPEN',          cmd=self._open_ds_folder,    color=C['dim'],   w=110,h=40).pack(side='left')

        SectionHdr(f,'DATASET FILES', C['green'])
        dc = mk_card(f, C['green'])
        self._ds_text = textbox(dc, height=20, color=C['green'])

        SectionHdr(f,'VOICE ANALYSIS', C['orange'])
        vc_ = mk_card(f, C['orange'])
        NeonBtn(vc_,'🔬  ANALYZE VOICE', cmd=self._analyze_voice,
                color=C['orange'],w=240,h=44).pack(pady=10)
        self._analysis_text = textbox(vc_, height=10, color=C['orange'])

        SectionHdr(f,'SO-VITS-SVC TRAINING ENGINE', C['purple'])
        tc = mk_card(f, C['purple'])
        tr = tk.Frame(tc, bg=C['card2']); tr.pack(fill='x', pady=8)
        self._train_btn = NeonBtn(tr,'🚀  TRAIN MODEL', cmd=self._start_training,
                                  color=C['purple'], w=210, h=44)
        self._train_btn.pack(side='left', padx=(0,10))
        self._stop_btn = NeonBtn(tr,'⏹  STOP', cmd=self._stop_training,
                                 color=C['red'], w=110, h=44)
        self._stop_btn.pack(side='left', padx=(0,10))
        NeonBtn(tr,'☁️  CLOUD TRAIN', cmd=self._cloud_train,
                color=C['cyan'], w=190, h=44).pack(side='left', padx=(0,10))
        NeonBtn(tr,'⚡  ONE-CLICK TRAIN', cmd=self._quick_cloud_train,
            color=C['green'], w=205, h=44).pack(side='left', padx=(0,10))
        NeonBtn(tr,'📥  INSTALL MODEL', cmd=self._install_model,
                color=C['green'], w=200, h=44).pack(side='left')
        tk.Label(tc,
                 text='☁️ Cloud Train: packages features → opens Google Drive + Colab (free T4 GPU, ~6-12 hrs).\n'
                      '📥 Install Model: imports a trained G_*.pth downloaded from Colab into the app.',
                 fg=C['dim'], bg=C['card2'], font=FONT['xs'], wraplength=900, justify='left'
                 ).pack(anchor='w', pady=(0,6))
        self._train_log = textbox(tc, height=14, color=C['purple'])

        # ── CLOUD TRAINING STATUS MONITOR ───────────────────────────────
        SectionHdr(f,'☁️ CLOUD TRAINING STATUS', C['cyan'])
        self._cloud_status_card = mk_card(f, C['cyan'])
        self._cloud_status_lbl = tk.Label(self._cloud_status_card,
            text='No active cloud training.\nClick ☁️ CLOUD TRAIN to start training on Kaggle or Google Colab.',
            fg=C['gray'], bg=C['card2'], font=FONT['body'], justify='left',
            wraplength=900)
        self._cloud_status_lbl.pack(anchor='w', pady=10)
        
        # Refresh button for status
        btn_row = tk.Frame(self._cloud_status_card, bg=C['card2'])
        btn_row.pack(anchor='w', pady=(0,10))
        NeonBtn(btn_row, '🔄 REFRESH STATUS', cmd=self._refresh_cloud_status,
                color=C['cyan'], w=180, h=36).pack(side='left', padx=(0,10))
        NeonBtn(btn_row, '📋 COPY LOG PATH', cmd=self._copy_log_path,
                color=C['dim'], w=160, h=36).pack(side='left')
        
        # Start auto-refresh timer
        self._cloud_status_timer = None
        self._start_cloud_status_refresh()

        self._refresh_ds()

    # ═══════════════════════════════════════════════════════════════
    #  PAGE: OUTPUTS
    # ═══════════════════════════════════════════════════════════════
    def _build_outputs(self):
        sf_ = ScrollableFrame(self._content)
        self._pages['outputs'] = sf_
        f = sf_.inner

        SectionHdr(f,'OUTPUT FILES', C['orange'])
        cc = mk_card(f, C['orange'])
        cr = tk.Frame(cc, bg=C['card2'])
        cr.pack(fill='x', pady=8)
        NeonBtn(cr,'🔄  REFRESH',   cmd=self._refresh_outputs,              color=C['orange'],w=150,h=42).pack(side='left',padx=(0,10))
        NeonBtn(cr,'📁  OPEN DIR',  cmd=lambda:self._open_dir(self.OUTPUT), color=C['cyan'],  w=150,h=42).pack(side='left',padx=(0,10))
        NeonBtn(cr,'🗑  CLEAR ALL', cmd=self._clear_all_outputs,            color=C['red'],   w=150,h=42).pack(side='left')

        self._out_list_host = tk.Frame(f, bg=C['bg'])
        self._out_list_host.pack(fill='x')
        self._refresh_outputs()

    # ─── FOOTER ───────────────────────────────────────────────────
    def _build_footer(self):
        ft = tk.Frame(self.root, bg=C['bg2'], height=62)
        ft.pack(fill='x', side='bottom')
        ft.pack_propagate(False)
        tk.Canvas(ft, height=1, bg=C['border'], highlightthickness=0).pack(fill='x')
        row = tk.Frame(ft, bg=C['bg2'])
        row.pack(fill='both', expand=True, padx=20, pady=8)
        self._status_lbl = tk.Label(row, textvariable=self.status_var,
                                    fg=C['cyan'], bg=C['bg2'], font=FONT['sm'])
        self._status_lbl.pack(side='left')
        self._foot_bar = NeonBar(row, w=380, h=14, color=C['cyan'], bg=C['bg2'])
        self._foot_bar.pack(side='left', padx=22)
        tk.Label(row, text='AI VOCALS STUDIO PRO  v4.0',
                 fg=C['dim'], bg=C['bg2'], font=FONT['xs']).pack(side='right')
        if not HAS_LIBROSA:
            tk.Label(row, text='⚠ librosa not found — pip install librosa',
                     fg=C['orange'], bg=C['bg2'], font=FONT['xs']).pack(side='right', padx=16)

    # ═══════════════════════════════════════════════════════════════
    #  GENERATE LOGIC
    # ═══════════════════════════════════════════════════════════════
    def _toggle_input(self):
        if self.input_type_var.get() == 'text':
            self._aud_sec.pack_forget()
            self._txt_sec.pack(fill='x')
        else:
            self._txt_sec.pack_forget()
            self._aud_sec.pack(fill='x')

    def _clr_ph(self, _=None):
        if self._text_box.get('1.0','end-1c') == 'Enter lyrics or speech text here...':
            self._text_box.delete('1.0','end')

    def _sel_audio(self):
        p = filedialog.askopenfilename(title='Select Audio',
            filetypes=[('Audio','*.wav *.mp3 *.flac *.m4a *.ogg'),('All','*.*')])
        if p:
            self.audio_path_var.set(p)
            self._audio_wave.load(p)
            self._log(f'📂 Loaded: {Path(p).name}')

    def _replace_song(self):
        """Replace a song's vocals with the selected trained clone."""
        song = self.audio_path_var.get().strip()
        name = self.model_var.get().strip()
        profile_path = self.MODELS / 'voices' / name / 'voice_profile.json'
        if not song or not Path(song).exists():
            messagebox.showwarning('No Song', 'Select a song first.')
            return
        if not name or not profile_path.exists():
            messagebox.showwarning(
                'No Saved Clone',
                'Select a saved voice clone from the model list first.')
            return
        if not self._rvc_engine.can_infer(name):
            messagebox.showerror(
                'RVC Model Required',
                'Indistinguishable song replacement requires a trained RVC model '
                'for this voice. Import or train one, then try again.')
            return
        threading.Thread(target=self._replace_song_worker,
                         args=(song, name, profile_path), daemon=True).start()

    def _replace_song_worker(self, song, name, profile_path):
        if self._generating:
            self._log('⚠ Already generating...')
            return
        self._generating = True
        try:
            from song_converter import change_song
            with open(profile_path) as handle:
                profile = json.load(handle)
            profile['voice_dir'] = str(profile_path.parent)
            out_dir = self.OUTPUT / name / 'song_replacements' / time.strftime('%Y%m%d_%H%M%S')
            self._badge('ENGINE: 🎵 Demucs + RVC', C['green'])
            self._log(f'⚡ Replacing vocals in: {Path(song).name}')
            output, steps = change_song(
                song, profile, out_dir, progress_cb=self._prog,
                separation='demucs', require_neural=True)
            self.last_output = Path(output)
            self._log(f'✅ Song replacement complete: {output}')
            self.root.after(0, lambda: self._out_wave.load(self.last_output))
            self.root.after(0, lambda: messagebox.showinfo(
                'Song Ready', f'Converted song saved to:\n{output}'))
            self._prog(f"✅ COMPLETE ({steps.get('conversion', 'RVC')})", 100)
        except Exception as exc:
            self._prog('❌ Song replacement failed', 0)
            self._log(f'❌ {exc}')
            self.root.after(0, lambda e=str(exc): messagebox.showerror(
                'Song Replacement Failed', e))
        finally:
            self._generating = False

    def _on_model_sel(self, _=None):
        name = self.model_var.get()
        if not name: return
        pp = self.MODELS/name/'voice_profile.json'
        saved_voice_profile = self.MODELS/'voices'/name/'voice_profile.json'
        # SO-VITS status prefix
        svc_badge = ''
        if self._engine:
            svc_badge = status_label(self._engine.model_status(name)) + '  |  '

        if pp.exists() or saved_voice_profile.exists():
            with open(pp if pp.exists() else saved_voice_profile) as f: p=json.load(f)
            self._model_info.config(
                text=svc_badge + f"Pitch: {p.get('avg_pitch',0):.0f}Hz  |  Tempo: {p.get('avg_tempo',0):.0f}BPM  |  Clips: {p.get('total_files',0)}",
                fg=C['cyan'])
        else:
            pr = self._get_persona(name)
            self._model_info.config(text=svc_badge + pr.get('desc','No profile'), fg=C['gray'])
        s = self._get_sample(name)
        if s: self._prev_wave.load(s)

    def _get_persona(self, name):
        k=name.lower()
        
        # First check if there's a custom voice profile
        model_dir = self.MODELS / k
        if model_dir.exists():
            voice_profile_file = model_dir / "voice_profile.json"
            if voice_profile_file.exists():
                try:
                    with open(voice_profile_file) as f:
                        profile = json.load(f)
                    # Extract characteristics for persona
                    if 'characteristics' in profile:
                        chars = profile['characteristics']
                        return {
                            'pitch': chars.get('pitch_shift', 0),
                            'speed': chars.get('speed', 1.0),
                            'reverb': chars.get('reverb', 0.1),
                            'gain': chars.get('gain', 0),
                            'eq_low': chars.get('eq_low', 1.0),
                            'eq_mid': chars.get('eq_mid', 1.0),
                            'eq_high': chars.get('eq_high', 1.0),
                            'desc': f"{profile.get('speaker', name)} – Custom voice clone"
                        }
                except Exception:
                    pass
        
        # Fall back to predefined personas
        if k in VOICE_PERSONAS: return VOICE_PERSONAS[k]
        for kk in VOICE_PERSONAS:
            if kk in k or k in kk: return VOICE_PERSONAS[kk]
        return VOICE_PERSONAS['default']

    def _get_sample(self, model_name):
        for d in [self.DATASET/model_name,
                  self.DATASET/model_name.replace('_custom_voice','').replace('_enhanced_voice',''),
                  self.MODELS/model_name/'samples']:
            if d.exists():
                for ext in ('*.wav','*.mp3','*.flac'):
                    fs=list(d.glob(ext))
                    if fs: return fs[0]
        return None

    def _preview_model(self):
        name=self.model_var.get()
        if not name: messagebox.showwarning('No Model','Select a model first.'); return
        s=self._get_sample(name)
        if s:
            self._log(f'▶ Previewing: {s.name}')
            self._prev_wave.load(s)
            self._prev_wave.set_active(True)
            threading.Thread(target=self._play_file, args=(str(s),), daemon=True).start()
        else:
            self._log(f'⚠ No samples for: {name}')
            messagebox.showinfo('No Samples',
                f"No audio found for '{name}'.\nAdd files via Training tab.")

    def _stop_preview(self):
        self._prev_wave.set_active(False)
        if self._preview_proc:
            try: self._preview_proc.kill()
            except: pass

    def _play_file(self, path):
        try:
            if sys.platform.startswith('linux'):
                self._preview_proc=subprocess.Popen(['xdg-open',path])
            elif sys.platform=='darwin':
                self._preview_proc=subprocess.Popen(['open',path])
            else:
                self._preview_proc=subprocess.Popen(['start',path],shell=True)
        except Exception as e:
            self._log(f'❌ Playback: {e}')

    def _generate(self):
        if self._generating: self._log('⚠ Already generating...'); return
        mode=self.input_type_var.get()
        if mode=='text':
            txt=self._text_box.get('1.0','end-1c').strip()
            if not txt or txt=='Enter lyrics or speech text here...':
                messagebox.showwarning('No Text','Enter some text.'); return
        else:
            if not self.audio_path_var.get():
                messagebox.showwarning('No Audio','Select an audio file.'); return
        if not self.model_var.get():
            messagebox.showwarning('No Model','Select a voice model.'); return
        threading.Thread(target=self._gen_worker, daemon=True).start()

    def _generate_over_beat(self):
        """Generate the selected text in the clone and mix it over the beat."""
        beat = self.audio_path_var.get().strip()
        name = self.model_var.get().strip()
        text = self._text_box.get('1.0', 'end-1c').strip()
        if not beat or not Path(beat).exists():
            messagebox.showwarning('No Beat', 'Select the beat in Audio Input first.')
            return
        if not name:
            messagebox.showwarning('No Voice', 'Select a voice model first.')
            return
        if not text or text == 'Enter lyrics or speech text here...':
            messagebox.showwarning('No Text', 'Enter lyrics or speech text first.')
            return
        threading.Thread(target=self._beat_worker,
                         args=(beat, name, text), daemon=True).start()

    def _quick_clone_over_beat(self):
        """Create a voice from source audio and place generated vocals on a beat."""
        dlg = tk.Toplevel(self.root)
        dlg.title('Quick Clone + Beat')
        dlg.configure(bg=C['bg2'])
        dlg.geometry('680x440')
        dlg.transient(self.root)
        dlg.grab_set()
        name_var = tk.StringVar()
        source_var = tk.StringVar()
        beat_var = tk.StringVar()
        type_var = tk.StringVar(value='speech')
        permission_var = tk.BooleanVar(value=False)
        fields = tk.Frame(dlg, bg=C['bg2'])
        fields.pack(fill='x', padx=24, pady=12)
        for row, label, variable in ((0, 'Voice name', name_var),
                                     (1, 'Voice source', source_var),
                                     (2, 'Beat/song', beat_var)):
            tk.Label(fields, text=label, fg=C['white'], bg=C['bg2'],
                     font=FONT['body']).grid(row=row, column=0, sticky='w', pady=7)
            tk.Entry(fields, textvariable=variable, bg=C['bg3'], fg=C['white'],
                     insertbackground=C['cyan'], relief='flat', width=46).grid(
                         row=row, column=1, padx=10, sticky='ew')

        def browse(variable, title):
            path = filedialog.askopenfilename(
                title=title,
                filetypes=[('Audio', '*.wav *.mp3 *.flac *.m4a *.ogg'),
                           ('All', '*.*')], parent=dlg)
            if path:
                variable.set(path)
                if variable is source_var and not name_var.get().strip():
                    name_var.set(Path(path).stem.replace(' ', '_'))

        NeonBtn(fields, 'BROWSE', cmd=lambda: browse(source_var, 'Choose voice source'),
                color=C['cyan'], w=110, h=30).grid(row=1, column=2)
        NeonBtn(fields, 'BROWSE', cmd=lambda: browse(beat_var, 'Choose beat/song'),
                color=C['cyan'], w=110, h=30).grid(row=2, column=2)
        tk.Label(dlg, text='Lyrics or text to perform', fg=C['white'],
                 bg=C['bg2'], font=FONT['body']).pack(anchor='w', padx=24)
        lyrics = textbox(dlg, height=5)
        lyrics.pack(fill='x', padx=24, pady=6)
        lyrics.insert('1.0', 'Enter lyrics or speech text here...')
        lyrics.bind('<FocusIn>', lambda _:
                    lyrics.delete('1.0', 'end') if lyrics.get(
                        '1.0', 'end-1c') == 'Enter lyrics or speech text here...' else None)
        options = tk.Frame(dlg, bg=C['bg2'])
        options.pack(fill='x', padx=24)
        tk.Label(options, text='Source type:', fg=C['gray'], bg=C['bg2'],
                 font=FONT['sm']).pack(side='left')
        for value, label in [('speech', 'Speech'), ('song', 'Song')]:
            tk.Radiobutton(options, text=label, variable=type_var, value=value,
                           fg=C['cyan'], bg=C['bg2'], selectcolor=C['bg3'],
                           activebackground=C['bg2'], font=FONT['sm']).pack(side='left', padx=8)
        tk.Checkbutton(
            dlg, text='I own this voice or have explicit permission to clone it',
            variable=permission_var, fg=C['orange'], bg=C['bg2'],
            selectcolor=C['bg3'], activebackground=C['bg2'],
            activeforeground=C['white'], font=FONT['sm']).pack(pady=8)

        def start():
            text = lyrics.get('1.0', 'end-1c').strip()
            if (not name_var.get().strip() or not Path(source_var.get()).exists()
                    or not Path(beat_var.get()).exists() or not text
                    or text == 'Enter lyrics or speech text here...'):
                messagebox.showwarning('Missing Information',
                                       'Provide a name, source, beat, and lyrics.', parent=dlg)
                return
            if not permission_var.get():
                messagebox.showwarning('Permission Required',
                                       'Confirm authorization to clone this voice.', parent=dlg)
                return
            dlg.destroy()
            threading.Thread(target=self._quick_clone_worker, args=(
                name_var.get().strip(), source_var.get(), beat_var.get(),
                text, type_var.get()), daemon=True).start()

        NeonBtn(dlg, 'CREATE + MIX', cmd=start, color=C['gold'],
                w=180, h=40).pack(side='left', padx=(180, 8), pady=8)
        NeonBtn(dlg, 'CANCEL', cmd=dlg.destroy, color=C['red'],
                w=100, h=40).pack(side='left', pady=8)

    def _quick_clone_worker(self, name, source, beat, text, source_type):
        """Build a clean profile, synthesize it, and mix it over the target beat."""
        if self._generating:
            self._log('⚠ Already generating...')
            return
        self._generating = True
        temp_voice = None
        try:
            from voice_cloner import build_voice_profile
            self._badge('ENGINE: 🎚 Demucs + Qwen3-TTS', C['green'])
            profile = build_voice_profile(
                name, source, source_type=source_type,
                voices_dir=self.MODELS / 'voices', progress_cb=self._prog,
                has_permission=True)
            if not profile:
                raise RuntimeError('Could not create a voice profile.')
            temp_voice = self._synth_text(text, name, self._mood_var.get())
            instrumental = AudioSegment.from_file(beat)
            mixed = instrumental.overlay(AudioSegment.from_file(temp_voice))
            out_dir = self.OUTPUT / name
            out_dir.mkdir(parents=True, exist_ok=True)
            output = out_dir / f'{Path(beat).stem}_{name}_quick_clone.wav'
            mixed.export(str(output), format='wav')
            self.last_output = output
            self.root.after(0, self._refresh_models)
            self.root.after(0, lambda: self._out_wave.load(output))
            self._prog('✅ QUICK CLONE + BEAT COMPLETE', 100)
            self._log(f'✅ Saved: {output}')
            self.root.after(0, lambda: messagebox.showinfo(
                'Beat Ready', f'Cloned vocal mixed over beat:\n{output}'))
        except Exception as exc:
            self._prog('❌ Quick clone failed', 0)
            self._log(f'❌ {exc}')
            self.root.after(0, lambda e=str(exc): messagebox.showerror(
                'Quick Clone Failed', e))
        finally:
            if temp_voice and os.path.exists(temp_voice):
                try:
                    os.unlink(temp_voice)
                except OSError:
                    pass
            self._generating = False

    def _beat_worker(self, beat, name, text):
        if self._generating:
            self._log('⚠ Already generating...')
            return
        self._generating = True
        temp_voice = None
        try:
            self._badge('ENGINE: 🧠 Clone + Beat Mix', C['green'])
            self._prog('🧠 Generating cloned vocal…', 10)
            temp_voice = self._synth_text(text, name, self._mood_var.get())
            vocal = AudioSegment.from_file(temp_voice)
            instrumental = AudioSegment.from_file(beat)
            mixed = instrumental.overlay(vocal)
            out_dir = self.OUTPUT / name
            out_dir.mkdir(parents=True, exist_ok=True)
            output = out_dir / f'{Path(beat).stem}_{name}_clone.wav'
            mixed.export(str(output), format='wav')
            self.last_output = output
            self._prog('✅ CLONE OVER BEAT COMPLETE', 100)
            self._log(f'✅ Beat mix saved: {output}')
            self.root.after(0, lambda: self._out_wave.load(output))
            self.root.after(0, lambda: messagebox.showinfo(
                'Beat Ready', f'Cloned vocal mixed over beat:\n{output}'))
        except Exception as exc:
            self._prog('❌ Beat mix failed', 0)
            self._log(f'❌ {exc}')
            self.root.after(0, lambda e=str(exc): messagebox.showerror(
                'Beat Mix Failed', e))
        finally:
            if temp_voice and os.path.exists(temp_voice):
                try:
                    os.unlink(temp_voice)
                except OSError:
                    pass
            self._generating = False

    def _gen_worker(self):
        self._generating=True; tmp=None
        try:
            self._prog('🔄 Initializing…',5)
            name=self.model_var.get(); mode=self.input_type_var.get()
            if mode=='text':
                txt=self._text_box.get('1.0','end-1c').strip()
                mood=self._mood_var.get()
                tmp=self._synth_text(txt, name, mood)
            else:
                tmp=self.audio_path_var.get()
                self._log(f'🎵 Audio: {Path(tmp).name}')

            od=self.OUTPUT/name; od.mkdir(exist_ok=True)
            base='text_vocal' if mode=='text' else Path(self.audio_path_var.get()).stem
            ts=time.strftime('%Y%m%d_%H%M%S')
            out_name=f'{base}_{name}_{ts}.wav'
            out=od/out_name

            # ── RVC v2 path (best for audio-to-audio) ─────────────
            pitch = int(self._fx['pitch'].get())
            if self._rvc_engine and self._rvc_engine.can_infer(name):
                self._log(f'🟣 RVC v2 inference: {name}')
                self._badge('ENGINE: 🎵 RVC v2', C['purple'])
                ok, err = self._rvc_engine.convert(
                    name, tmp, str(out),
                    pitch_shift=pitch,
                    progress_cb=self._prog,
                )
                if not ok:
                    raise RuntimeError(f'RVC v2: {err}')
            # ── SO-VITS fallback ───────────────────────────────────
            elif self._engine and self._engine.can_infer(name):
                self._log(f'🟢 SO-VITS inference: {name}')
                self._badge('ENGINE: 🔄 SO-VITS', C['cyan'])
                ok, err = self._engine.convert(
                    name, tmp, str(out),
                    pitch_shift=pitch,
                    f0_method='dio',
                    progress_cb=self._prog,
                )
                if not ok:
                    raise RuntimeError(f'SO-VITS: {err}')
            else:
                saved_voice = self.MODELS/'voices'/name/'voice_profile.json'
                if saved_voice.exists():
                    raise RuntimeError(
                        'Audio-to-audio cloning needs a trained RVC or SO-VITS model. '
                        'This voice has a neural TTS reference only; use Text mode or '
                        'train/import an authorized RVC model.'
                    )
                # ── DSP fallback ───────────────────────────────────
                self._log('🟡 DSP fallback (no trained model)')
                self._badge('ENGINE: 🎛️ DSP Fallback', C['orange'])
                self._prog('🎵 Loading audio…',38)
                audio=AudioSegment.from_file(tmp).normalize()
                self._prog('✨ Applying voice profile…',58)
                persona=dict(self._get_persona(name))
                persona['pitch']  += self._fx['pitch'].get()
                persona['speed']  *= self._fx['speed'].get()
                persona['reverb']  = self._fx['reverb'].get() if self._fx['reverb'].get()!=0.05 else persona['reverb']
                persona['gain']   += (self._fx['bass'].get()-1.0)*4
                audio=self._transform(audio, persona)
                self._prog('💾 Saving…',85)
                audio.export(str(out), format='wav')

            if out.exists() and out.stat().st_size>500:
                self.last_output=out
                self.root.after(0,lambda:self._out_wave.load(out))
                try:
                    info=sf.info(str(out)); dur=info.duration
                except Exception:
                    dur=out.stat().st_size/88200
                sz=out.stat().st_size/1024
                self._prog('✅ COMPLETE!',100)
                self._log(f'✅ {out_name}')
                self._log(f'   {dur:.1f}s  |  {sz:.1f}KB  →  output/{name}/')
                self.root.after(0,lambda:self._out_lbl.config(text=f'Latest: {out_name}',fg=C['green']))
                self._refresh_outputs()
                if messagebox.askyesno('✅ Done!',f'{out_name}\n{dur:.1f}s | {sz:.1f}KB\n\nPlay now?'):
                    self._play_output()
            else:
                raise RuntimeError('Output file empty or missing')
        except Exception as e:
            self._prog('❌ Error',0)
            self._log(f'❌ {e}')
            messagebox.showerror('Error',str(e))
        finally:
            if tmp and self.input_type_var.get()=='text' and os.path.exists(tmp):
                try: os.unlink(tmp)
                except: pass
            self._generating=False

    def _tts(self,text):
        tts=gTTS(text=text,lang='en',slow=False)
        with tempfile.NamedTemporaryFile(delete=False,suffix='.mp3') as f:
            tts.save(f.name); mp3=f.name
        seg=AudioSegment.from_mp3(mp3); os.unlink(mp3)
        wav=mp3.replace('.mp3','.wav')
        seg.export(wav,format='wav',parameters=['-ar','44100'])
        return wav

    def _synth_text(self, text: str, model_name: str, mood: str) -> str:
        """
        Generate speech for text input.
        Priority: ElevenLabs → XTTS v2 → gTTS (DSP fallback).
        Returns temp WAV path.
        """
        base_dir = str(self.MODELS.parent.resolve())

        # Paid services stay opt-in; the default route is fully local/free.
        if os.environ.get('ALLOW_PAID_ENGINES', '').lower() in ('1', 'true', 'yes'):
            try:
                from elevenlabs_engine import ElevenLabsEngine
                el = ElevenLabsEngine(base_dir)
                if el.can_synthesize():
                    self._badge('ENGINE: ⚡ ElevenLabs', C['gold'])
                    self._prog('⚡ ElevenLabs synthesizing…', 15)
                    out = el.synthesize(text, model_name, mood=mood, progress_cb=self._prog)
                    self._log(f'⚡ ElevenLabs done: {len(text)} chars, mood={mood}')
                    return str(out)
            except Exception as e:
                self._log(f'ℹ️ ElevenLabs: {type(e).__name__}: {e}')

        # ── 2. Qwen3-TTS (real neural clone — installed, local) ───
        try:
            from qwen3_tts_engine import Qwen3TTSEngine, load_voice_dir
            qe = Qwen3TTSEngine()
            if qe.can_clone():
                ref = self._custom_ref_path
                if not ref or not os.path.exists(str(ref)):
                    prof = load_voice_dir(model_name)
                    ref = (prof or {}).get('reference')
                if ref and os.path.exists(str(ref)):
                    self._badge('ENGINE: 🧠 Qwen3-TTS Clone', C['green'])
                    self._prog('🧠 Qwen3-TTS synthesizing…', 20)
                    out = qe.clone_voice(
                        ref_audio=str(ref), ref_text=None, target_text=text,
                        speaker_name=model_name, progress_cb=self._prog,
                        has_permission=True,
                    )
                    if out and os.path.exists(out):
                        self._log(f'🧠 Qwen3-TTS done: {len(text)} chars')
                        return str(out)
        except Exception as e:
            self._log(f'ℹ️ Qwen3-TTS: {type(e).__name__}: {e}')

        # ── 3. XTTS v2 (free, local) ──────────────────────────────
        try:
            from xtts_engine import XttsEngine
            xe = XttsEngine(base_dir)
            if xe.can_synthesize():
                self._badge('ENGINE: ⚡ XTTS Clone', C['green'])
                self._prog('⚡ XTTS v2 synthesizing…', 20)
                out = xe.synthesize(
                    text, model_name,
                    mood=mood,
                    custom_ref=self._custom_ref_path,
                    progress_cb=self._prog,
                )
                self._log(f'⚡ XTTS done: {len(text)} chars, mood={mood}')
                return str(out)
        except Exception as e:
            self._log(f'ℹ️ XTTS: {type(e).__name__}: {e}')

        # ── 3. gTTS fallback ──────────────────────────────────────
        self._badge('ENGINE: 🎛️ DSP Fallback', C['orange'])
        self._prog('🔤 Running gTTS…', 20)
        tmp = self._tts(text)
        self._log(f'📝 gTTS done: {len(text)} chars')
        return tmp

    def _pick_custom_ref(self):
        """Open a file picker to choose a custom XTTS reference audio clip."""
        path = filedialog.askopenfilename(
            title='Select Reference Audio for XTTS',
            filetypes=[('Audio', '*.wav *.mp3 *.flac *.ogg'), ('All files', '*.*')],
        )
        if path:
            self._custom_ref_path = path
            self._log(f'📎 Custom ref set: {Path(path).name}')
            self._badge('ENGINE: ⚡ XTTS (custom ref)', C['green'])

    def _badge(self, text: str, color: str):
        """Thread-safe update of the engine badge label."""
        try:
            self.root.after(0, lambda t=text, c=color: self._engine_badge.config(text=t, fg=c))
        except Exception:
            pass

    def _setup_el_key(self):
        """Dialog to save ElevenLabs API key to .cloud_config."""
        cfg = Path('.cloud_config')
        cur = ''
        if cfg.exists():
            for line in cfg.read_text().splitlines():
                if line.startswith('ELEVENLABS_API_KEY='):
                    cur = line.split('=', 1)[1].strip().strip('"').strip("'")
                    break
        # Show masked hint if key already exists
        hint = (cur[:8] + '…') if len(cur) > 8 else cur
        key = simpledialog.askstring(
            'ElevenLabs API Key',
            f'Paste your ElevenLabs API key.\n'
            f'Saved to .cloud_config (git-ignored).\n\n'
            f'Get key → elevenlabs.io/app → Profile → API Keys\n\n'
            f'Current: {hint or "(none)"}',
            parent=self.root,
        )
        if not key or not key.strip() or key.strip().endswith('…'):
            return
        key = key.strip()
        # Update .cloud_config
        lines = cfg.read_text().splitlines() if cfg.exists() else []
        new_lines = [l for l in lines if not l.startswith('ELEVENLABS_API_KEY=')]
        new_lines.append(f'ELEVENLABS_API_KEY={key}')
        cfg.write_text('\n'.join(new_lines) + '\n')
        self._log('✅ ElevenLabs API key saved to .cloud_config')
        self._badge('ENGINE: ⚡ ElevenLabs (key saved — generate to test)', C['gold'])

    def _transform(self, audio, persona):
        pitch=persona.get('pitch',0); speed=persona.get('speed',1.0)
        reverb=persona.get('reverb',0.0); gain=persona.get('gain',0)
        if HAS_LIBROSA and (pitch!=0 or speed!=1.0):
            samples=np.array(audio.get_array_of_samples(),dtype=np.float32)
            samples/=(2**(audio.sample_width*8-1))
            sr=audio.frame_rate
            if audio.channels>1:
                samples=samples.reshape(-1,audio.channels).mean(axis=1)
            if pitch!=0:
                samples=librosa.effects.pitch_shift(samples,sr=sr,n_steps=float(pitch))
            if speed!=1.0:
                samples=librosa.effects.time_stretch(samples,rate=float(speed))
            samples=np.clip(samples*32767,-32768,32767).astype(np.int16)
            audio=AudioSegment(samples.tobytes(),frame_rate=sr,sample_width=2,channels=1)
        else:
            if pitch!=0:
                factor=2**(pitch/12.0)
                audio=audio._spawn(audio.raw_data,
                                   overrides={'frame_rate':int(audio.frame_rate*factor)})
                audio=audio.set_frame_rate(44100)
            if speed!=1.0:
                audio=audio.speedup(playback_speed=speed)
        if gain!=0:
            audio=audio+gain
        if reverb>0.02:
            delay=int(70*reverb)
            echo=audio-int(5+reverb*5)
            try: audio=audio.overlay(echo,position=delay)
            except: pass
        return audio

    def _play_output(self):
        if not self.last_output or not self.last_output.exists():
            messagebox.showinfo('No Output','Generate audio first.'); return
        self._out_wave.set_active(True)
        threading.Thread(target=self._play_file,args=(str(self.last_output),),daemon=True).start()
        threading.Thread(target=self._vu_anim, daemon=True).start()

    def _vu_anim(self):
        for _ in range(200):
            self._vu.push(random.uniform(0.2,0.88))
            time.sleep(0.05)
        self._out_wave.set_active(False)

    def _open_out_folder(self):
        d=self.OUTPUT/(self.model_var.get() or '')
        self._open_dir(d if d.exists() else self.OUTPUT)

    # ═══════════════════════════════════════════════════════════════
    #  MODELS LOGIC
    # ═══════════════════════════════════════════════════════════════
    def _refresh_models(self):
        models=[]
        for item in sorted(self.MODELS.iterdir()):
            if item.is_file() and item.suffix=='.pth':
                models.append(item.stem)
            elif item.is_dir():
                for sub in item.iterdir():
                    if sub.suffix=='.pth':
                        models.append(item.name); break
        # Saved neural clones are profiles, not training checkpoints.
        voices_dir = self.MODELS/'voices'
        if voices_dir.is_dir():
            models.extend(
                voice.name for voice in sorted(voices_dir.iterdir())
                if voice.is_dir() and (voice/'voice_profile.json').exists()
            )
        models = list(dict.fromkeys(models))
        self._gen_cb['values']=models
        if hasattr(self,'_train_cb'): self._train_cb['values']=models
        if models and not self.model_var.get():
            self.model_var.set(models[0]); self._on_model_sel()
        self._rebuild_model_cards(models)
        self._log(f'🔍 {len(models)} model(s) found')
        self._prog(f'✅ {len(models)} models loaded',100)

    def _rebuild_model_cards(self, models):
        for w in self._model_cards_host.winfo_children(): w.destroy()
        if not models:
            tk.Label(self._model_cards_host,
                     text='No models found.  Import a .pth file or create one via Training.',
                     fg=C['gray'],bg=C['bg'],font=FONT['body']).pack(pady=24)
            return
        for name in models: self._model_card(name)

    def _model_card(self, name):
        c = AniCard(self._model_cards_host, accent=C['purple'])
        c.pack(fill='x', padx=14, pady=5)
        inner = c.inner

        info = tk.Frame(inner, bg=C['card2'])
        info.pack(side='left', fill='x', expand=True)
        tk.Label(info,text=name,fg=C['purple'],bg=C['card2'],font=FONT['h2']).pack(anchor='w')
        ds=self.DATASET/name
        n=sum(len(list(ds.glob(f'*{e}'))) for e in ('.wav','.mp3','.flac')) if ds.exists() else 0
        s=self._get_sample(name)
        meta=f'Training clips: {n}'
        if s: meta+=f'   ·   Preview: {s.name}'
        tk.Label(info,text=meta,fg=C['gray'],bg=C['card2'],font=FONT['sm']).pack(anchor='w')
        if self._engine:
            badge = status_label(self._engine.model_status(name))
            badge_color = C['green'] if 'READY' in badge else C['orange'] if 'PLACEHOLDER' in badge or 'MISSING config' in badge or 'UNTRAINED' in badge else C['red']
        else:
            badge = '⚪ DSP MODE (svc_engine unavailable)'
            badge_color = C['dim']
        tk.Label(info,text=badge,fg=badge_color,bg=C['card2'],font=FONT['xs']).pack(anchor='w')

        br=tk.Frame(inner,bg=C['card2'])
        br.pack(side='right')
        NeonBtn(br,'▶ PREVIEW',cmd=lambda n=name:self._prev_by_name(n),color=C['green'],w=125,h=36).pack(side='left',padx=(0,8))
        NeonBtn(br,'SELECT',   cmd=lambda n=name:self._sel_model(n),   color=C['purple'],w=100,h=36).pack(side='left',padx=(0,8))
        NeonBtn(br,'🗑',       cmd=lambda n=name:self._del_model(n),   color=C['red'],  w=44, h=36).pack(side='left')

    def _prev_by_name(self,name):
        self.model_var.set(name); self._preview_model()

    def _sel_model(self,name):
        self.model_var.set(name); self._on_model_sel()
        self._show('generate'); self._log(f'✅ Model: {name}')

    def _del_model(self,name):
        if messagebox.askyesno('Delete',f"Delete '{name}'?"):
            for p in [self.MODELS/name, self.MODELS/f'{name}.pth']:
                if p.is_dir(): shutil.rmtree(p)
                elif p.is_file(): p.unlink()
            self._refresh_models(); self._log(f'🗑 Deleted: {name}')

    def _import_model_file(self):
        p=filedialog.askopenfilename(title='Import Model',
            filetypes=[('PTH','*.pth'),('All','*.*')])
        if p:
            shutil.copy2(p,self.MODELS/Path(p).name)
            self._refresh_models(); self._log(f'📥 Imported: {Path(p).name}')

    def _import_model_folder(self):
        p=filedialog.askdirectory(title='Import Model Folder')
        if p:
            src=Path(p)
            shutil.copytree(str(src),str(self.MODELS/src.name),dirs_exist_ok=True)
            self._refresh_models(); self._log(f'📥 Folder: {src.name}')

    def _create_voice_profile(self):
        """Create a saved voice profile from one guided dialog."""
        dlg = tk.Toplevel(self.root)
        dlg.title('Create Voice')
        dlg.configure(bg=C['bg2'])
        dlg.geometry('600x300')
        dlg.transient(self.root)
        dlg.grab_set()

        name_var = tk.StringVar()
        source_var = tk.StringVar()
        type_var = tk.StringVar(value='speech')
        permission_var = tk.BooleanVar(value=False)

        tk.Label(dlg, text='CREATE AUTHORIZED VOICE', fg=C['green'],
                 bg=C['bg2'], font=FONT['h2']).pack(pady=(18, 10))
        form = tk.Frame(dlg, bg=C['bg2'])
        form.pack(fill='x', padx=24)
        tk.Label(form, text='Name', fg=C['white'], bg=C['bg2'],
                 font=FONT['body']).grid(row=0, column=0, sticky='w', pady=6)
        tk.Entry(form, textvariable=name_var, bg=C['bg3'], fg=C['white'],
                 insertbackground=C['cyan'], relief='flat', width=42).grid(
                     row=0, column=1, columnspan=2, sticky='ew', padx=10)
        tk.Label(form, text='Reference', fg=C['white'], bg=C['bg2'],
                 font=FONT['body']).grid(row=1, column=0, sticky='w', pady=6)
        tk.Entry(form, textvariable=source_var, bg=C['bg3'], fg=C['white'],
                 insertbackground=C['cyan'], relief='flat', width=34).grid(
                     row=1, column=1, sticky='ew', padx=10)

        def browse():
            path = filedialog.askopenfilename(
                title='Choose clean voice reference',
                filetypes=[('Audio', '*.wav *.mp3 *.flac *.m4a *.ogg'),
                           ('All', '*.*')], parent=dlg)
            if path:
                source_var.set(path)
                if not name_var.get().strip():
                    name_var.set(Path(path).stem.replace(' ', '_'))

        NeonBtn(form, 'BROWSE', cmd=browse, color=C['cyan'],
                w=105, h=30).grid(row=1, column=2, padx=(0, 0))
        tk.Label(form, text='Type', fg=C['white'], bg=C['bg2'],
                 font=FONT['body']).grid(row=2, column=0, sticky='w', pady=6)
        for value, label in [('speech', 'Speech'), ('song', 'Song')]:
            tk.Radiobutton(form, text=label, variable=type_var, value=value,
                           fg=C['cyan'], bg=C['bg2'], selectcolor=C['bg3'],
                           activebackground=C['bg2'], font=FONT['sm']).grid(
                               row=2, column=1 if value == 'speech' else 2,
                               sticky='w', padx=10)
        tk.Checkbutton(
            dlg, text='I own this voice or have explicit permission to clone it',
            variable=permission_var, fg=C['orange'], bg=C['bg2'],
            selectcolor=C['bg3'], activebackground=C['bg2'],
            activeforeground=C['white'], font=FONT['sm']).pack(pady=8)

        def worker():
            try:
                from voice_cloner import build_voice_profile
                profile = build_voice_profile(
                    name_var.get().strip(), source_var.get(),
                    source_type=type_var.get(),
                    voices_dir=self.MODELS / 'voices',
                    progress_cb=self._prog, has_permission=True)
                if not profile:
                    raise RuntimeError('Voice profile could not be created.')
                self._log(f"✅ Voice profile ready: {profile['name']}")
                self.root.after(0, self._refresh_models)
                self.root.after(0, lambda: messagebox.showinfo(
                    'Voice Created',
                    f"{profile['name']} is ready for neural TTS.\n\n"
                    'Train or import its RVC model for one-click song replacement.'))
            except Exception as exc:
                self._log(f'❌ Voice creation failed: {exc}')
                self.root.after(0, lambda e=str(exc): messagebox.showerror(
                    'Voice Creation Failed', e))

        def create():
            if not name_var.get().strip() or not Path(source_var.get()).exists():
                messagebox.showwarning('Missing Information',
                                       'Enter a name and choose an audio file.',
                                       parent=dlg)
                return
            if not permission_var.get():
                messagebox.showwarning('Permission Required',
                                       'Confirm authorization to clone this voice.',
                                       parent=dlg)
                return
            dlg.destroy()
            threading.Thread(target=worker, daemon=True).start()

        NeonBtn(dlg, 'CREATE VOICE', cmd=create, color=C['green'],
                w=180, h=40).pack(side='left', padx=(150, 8), pady=10)
        NeonBtn(dlg, 'CANCEL', cmd=dlg.destroy, color=C['red'],
                w=100, h=40).pack(side='left', pady=10)

    # ═══════════════════════════════════════════════════════════════
    #  TRAINING LOGIC
    # ═══════════════════════════════════════════════════════════════
    def _tlog(self, msg):
        """Append a line to the training log widget (thread-safe)."""
        def _do():
            try:
                self._train_log.config(state='normal')
                self._train_log.insert('end', msg + '\n')
                self._train_log.see('end')
                self._train_log.config(state='disabled')
            except Exception:
                pass
        self.root.after(0, _do)

    def _start_training(self):
        if not self._engine:
            messagebox.showerror('Error','svc_engine not available'); return
        name = self.train_model_var.get()
        if not name:
            messagebox.showwarning('No Model','Select a target model first.'); return
        self._train_stop.clear()
        def _cb(msg, pct):
            self._tlog(msg)
            if pct >= 0:
                self.root.after(0, lambda p=pct: self._foot_bar.set(p))
        def _worker():
            self._tlog(f'─── Starting SO-VITS training: {name} ───')
            ok, err = self._engine.train(name, progress_cb=_cb, stop_event=self._train_stop)
            if ok:
                self._tlog('✅ Training complete! Model saved to models/')
                self.root.after(0, self._refresh_models)
                self.root.after(0, lambda: messagebox.showinfo('Training Done',
                    f'{name} trained successfully!\nModel saved to models/{name}/'))
            else:
                self._tlog(f'❌ Training failed: {err}')
                self.root.after(0, lambda e=err: messagebox.showerror('Training Failed', e))
        threading.Thread(target=_worker, daemon=True).start()
        self._tlog(f'▶ Training thread started for: {name}')

    def _stop_training(self):
        self._train_stop.set()
        self._tlog('⏹ Stop signal sent — waiting for process to exit…')

    def _quick_cloud_train(self):
        """Validate the cleaned dataset, then open the free cloud trainer."""
        name = self.train_model_var.get().strip()
        if not name:
            messagebox.showwarning('No Model', 'Select a target model first.')
            return
        try:
            from rvc_training import validate_training_dataset
            report = validate_training_dataset(self.DATASET / name)
        except Exception as exc:
            messagebox.showerror('Dataset Check Failed', str(exc))
            return
        if not report['ready']:
            messagebox.showwarning(
                'More Voice Data Needed',
                f"Found {report['file_count']} files and {report['duration_s']:.1f} seconds.\n\n"
                'Add at least 3 clean vocal clips totaling 90 seconds, then try again.')
            return
        self._tlog(
            f"✅ Dataset ready: {report['file_count']} clips, "
            f"{report['duration_s']:.1f}s, quality {report['quality_score']:.2f}")
        self._cloud_train()

    def _get_kaggle_trainer(self):
        """Return a KaggleTrainer, running first-time setup if needed."""
        try:
            from kaggle_trainer import KaggleTrainer
        except ImportError:
            messagebox.showerror('Missing Module',
                'kaggle_trainer.py not found in the app directory.'); return None
        kt = KaggleTrainer(Path(__file__).parent)
        if not kt.configured:
            self._kaggle_setup(kt)
        return kt if kt.configured else None

    def _kaggle_setup(self, kt=None):
        """One-time setup dialog — user drops in their kaggle.json."""
        import subprocess as _sp
        dlg = tk.Toplevel(self.root)
        dlg.title('☁️ Kaggle Setup — One Time Only')
        dlg.configure(bg=C['bg2']); dlg.geometry('560x340')
        dlg.transient(self.root); dlg.grab_set()

        tk.Label(dlg, text='☁️  FREE GPU TRAINING SETUP', fg=C['cyan'],
                 bg=C['bg2'], font=FONT['h2']).pack(pady=(18,4))
        tk.Label(dlg,
            text='Kaggle gives you a free P100 GPU (faster than Colab T4).\n'
                 'One-time setup — takes 2 minutes:\n\n'
                 '  1. Go to  kaggle.com  → sign in (free account)\n'
                 '  2. Click your avatar → Settings → API → Create New Token\n'
                 '  3. A file called  kaggle.json  downloads\n'
                 '  4. Click the button below and pick that file',
            fg=C['white'], bg=C['bg2'], font=FONT['body'],
            justify='left', wraplength=520).pack(padx=20, pady=6)

        status_var = tk.StringVar(value='')
        tk.Label(dlg, textvariable=status_var, fg=C['green'],
                 bg=C['bg2'], font=FONT['body']).pack(pady=4)

        def pick_json():
            p = filedialog.askopenfilename(
                title='Select kaggle.json',
                filetypes=[('JSON', '*.json'), ('All', '*.*')]
            )
            if not p: return
            try:
                if kt is None:
                    from kaggle_trainer import KaggleTrainer
                    _kt = KaggleTrainer(Path(__file__).parent)
                else:
                    _kt = kt
                _kt.setup_from_file(p)
                status_var.set(f'✅ Saved! Username: {_kt.kaggle_username()}')
                self.root.after(1500, dlg.destroy)
            except Exception as e:
                status_var.set(f'❌ {e}')

        def open_kaggle():
            _sp.Popen(['xdg-open', 'https://www.kaggle.com/settings'],
                      env={**os.environ, 'DISPLAY': os.environ.get('DISPLAY', ':0')})

        br = tk.Frame(dlg, bg=C['bg2']); br.pack(pady=10)
        NeonBtn(br, '🌐  Open Kaggle Settings', cmd=open_kaggle,
                color=C['dim'], w=220, h=40).pack(side='left', padx=8)
        NeonBtn(br, '📂  Pick kaggle.json', cmd=pick_json,
                color=C['cyan'], w=200, h=40).pack(side='left', padx=8)

    def _cloud_train(self):
        name = self.train_model_var.get()
        if not name:
            messagebox.showwarning('No Model', 'Select a target model first.'); return

        # Create custom dialog with both options
        dlg = tk.Toplevel(self.root)
        dlg.title('☁️ Auto Cloud Training')
        dlg.configure(bg=C['bg2'])
        dlg.geometry('500x420')
        dlg.transient(self.root)
        dlg.grab_set()
        
        tk.Label(dlg, text='☁️  AUTO CLOUD TRAINING', fg=C['cyan'],
                bg=C['bg2'], font=FONT['h2']).pack(pady=(20,10))
        
        tk.Label(dlg, 
                text=f'Train "{name}" automatically on free GPU:\n\n'
                     'Both methods prepare the zip and handle setup.',
                fg=C['white'], bg=C['bg2'], font=FONT['body'], 
                wraplength=450, justify='center').pack(pady=10)
        
        # Kaggle option
        kf = tk.Frame(dlg, bg=C['card2'], padx=20, pady=15)
        kf.pack(fill='x', padx=20, pady=10)
        tk.Label(kf, text='🚀 KAGGLE P100', fg=C['green'], 
                bg=C['card2'], font=FONT['h3']).pack(anchor='w')
        tk.Label(kf, text='Fully automated\n~8-10 hours\nRequires kaggle.json setup',
                fg=C['gray'], bg=C['card2'], font=FONT['sm'], 
                justify='left').pack(anchor='w', pady=(5,0))
        
        def start_kaggle():
            dlg.destroy()
            self._cloud_train_kaggle(name)
        
        NeonBtn(kf, 'START KAGGLE', cmd=start_kaggle,
               color=C['green'], w=160, h=36).pack(anchor='e', pady=(5,0))
        
        # Colab option
        cf = tk.Frame(dlg, bg=C['card2'], padx=20, pady=15)
        cf.pack(fill='x', padx=20, pady=10)
        tk.Label(cf, text='🌐 GOOGLE COLAB T4', fg=C['purple'], 
                bg=C['card2'], font=FONT['h3']).pack(anchor='w')
        tk.Label(cf, text='Auto-opens browser, manual upload\n~10-12 hours\nMost reliable',
                fg=C['gray'], bg=C['card2'], font=FONT['sm'], 
                justify='left').pack(anchor='w', pady=(5,0))
        
        def start_colab():
            dlg.destroy()
            self._cloud_train_colab(name)
        
        NeonBtn(cf, 'START COLAB', cmd=start_colab,
               color=C['purple'], w=160, h=36).pack(anchor='e', pady=(5,0))
        
        # Cancel button
        tk.Label(dlg, text='Training runs in background. You can close the app.',
                fg=C['dim'], bg=C['bg2'], font=FONT['xs']).pack(pady=(15,5))
        
        NeonBtn(dlg, 'CANCEL', cmd=dlg.destroy,
               color=C['red'], w=100, h=32).pack(pady=5)

    def _start_auto_train(self, model_name, method):
        """Start automated training with the unified trainer."""
        self._train_stop.clear()
        self._tlog(f'☁️ Starting {method.upper()} auto-training for: {model_name}')
        
        def progress_cb(msg, pct):
            self._tlog(msg)
            if pct >= 0:
                self.root.after(0, lambda p=pct: self._foot_bar.set(p))
        
        def worker():
            try:
                # Import and run auto trainer
                sys.path.insert(0, str(Path(__file__).parent))
                from auto_train import AutoTrainer
                
                trainer = AutoTrainer(model_name)
                trainer.set_progress_callback(progress_cb)
                
                if method == 'kaggle':
                    ok, result = trainer.train_kaggle(stop_event=self._train_stop)
                else:
                    ok, result = trainer.train_colab()
                
                if ok:
                    if result == 'colab_started':
                        self._tlog('🌐 Colab opened in browser')
                        self._tlog('   Upload the zip from Desktop when prompted')
                        self.root.after(0, lambda: self._foot_bar.set(25))
                    else:
                        self._tlog(f'🎉 Training complete! Model: {result}')
                        self.root.after(0, self._refresh_models)
                        self.root.after(0, lambda: messagebox.showinfo(
                            'Training Complete!', 
                            f'Model trained successfully!\n\nSaved to: {result}'))
                else:
                    self._tlog(f'❌ Training failed: {result}')
                    if '401' in str(result) or 'Unauthorized' in str(result):
                        self._tlog('   → Try Google Colab instead (more reliable)')
                    self.root.after(0, lambda e=result: messagebox.showerror(
                        'Training Failed', str(e)[:500]))
                    
            except Exception as e:
                self._tlog(f'❌ Error: {e}')
                import traceback
                self._tlog(traceback.format_exc()[:500])
        
        threading.Thread(target=worker, daemon=True).start()

    def _cloud_train_kaggle(self, name: str):
        kt = self._get_kaggle_trainer()
        if kt is None: return

        self._train_stop.clear()
        self._tlog(f'☁️ Starting automated Kaggle training for: {name}')

        def _cb(msg, pct):
            self._tlog(msg)
            if pct >= 0:
                self.root.after(0, lambda p=pct: self._foot_bar.set(p))

        def _worker():
            ok, result = kt.train(name, progress_cb=_cb, stop_event=self._train_stop)
            if ok:
                self._tlog(f'🎉 Training complete! Model ready in models/{name}/')
                self.root.after(0, self._refresh_models)
                self.root.after(0, lambda: messagebox.showinfo('Training Done!',
                    f'"{name}" trained successfully!\n\n'
                    'Switch to the Generate tab and select it.'))
            else:
                self._tlog(f'❌ Kaggle failed: {result}')
                if '401' in str(result) or 'Unauthorized' in str(result):
                    self._tlog('   → Try Google Colab instead (click ☁️ CLOUD TRAIN → NO)')
                self.root.after(0, lambda e=result: messagebox.showerror(
                    'Kaggle Failed',
                    f'{e}\n\nTry Google Colab instead:\nClick ☁️ CLOUD TRAIN and choose NO.'
                ))

        threading.Thread(target=_worker, daemon=True).start()

    def _cloud_train_colab(self, name: str):
        """Open browser tabs for Colab training and package the zip."""
        import shutil as _shutil
        base = Path(__file__).parent
        zip_src = base / f'{name}_colab_training.zip'

        # Build zip if missing
        if not zip_src.exists():
            self._tlog('📦 Packaging training data for Colab...')
            try:
                from kaggle_trainer import KaggleTrainer
                kt = KaggleTrainer(base)
                zip_src = kt._package(name)
                # Copy to base dir for easy access
                dst = base / f'{name}_colab_training.zip'
                _shutil.copy(zip_src, dst)
                zip_src = dst
            except Exception as exc:
                self._tlog(f'❌ Packaging failed: {exc}'); return

        # Copy to Desktop for easy upload
        desktop = Path.home() / 'Desktop'
        if desktop.exists():
            try:
                dst = desktop / zip_src.name
                _shutil.copy(zip_src, dst)
                self._tlog(f'📁 Zip copied to Desktop: {dst.name}')
            except Exception:
                pass

        zip_gb = zip_src.stat().st_size / 1e9
        self._tlog(f'📦 Training zip ready: {zip_src.name}  ({zip_gb:.1f} GB)')
        self._tlog('🌐 Opening Google Drive + Colab in your browser...')

        colab_url = ('https://colab.research.google.com/github/'
                     'airbearme/ai-vocals-studio/blob/main/colab/Pacaveli_Training.ipynb')
        drive_url = 'https://drive.google.com/drive/my-drive'

        env = dict(os.environ, DISPLAY=os.environ.get('DISPLAY', ':0'))
        subprocess.Popen(['xdg-open', drive_url],  stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL, env=env)
        subprocess.Popen(['xdg-open', colab_url], stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL, env=env)

        messagebox.showinfo('☁️ Colab Training — Steps',
            f'Zip ready on Desktop: {zip_src.name}  ({zip_gb:.1f} GB)\n\n'
            '═══ DO THESE STEPS IN YOUR BROWSER ═══\n\n'
            '1. COLAB tab: Runtime → Change runtime type → T4 GPU → Save\n\n'
            '2. COLAB: Run Cell 1 (GPU check) and Cell 2 (install deps)\n\n'
            '3. COLAB Cell 4: click ▶ and upload the zip from your Desktop\n'
            f'   File: {zip_src.name}\n\n'
            '4. COLAB: Run all remaining cells (Ctrl+F9)\n\n'
            '5. Training runs 6-12 hours.  Model auto-downloads when done.\n\n'
            '═══ AFTER TRAINING ═══\n'
            'Click 📥 INSTALL MODEL here and select the downloaded G_*.pth.\n'
            'config.json from the same folder is auto-imported.'
        )

    def _install_model(self):
        import shutil
        name = self.train_model_var.get()
        pth = filedialog.askopenfilename(
            title='Select trained G_*.pth from Colab',
            filetypes=[('PyTorch checkpoint', '*.pth'), ('All files', '*.*')]
        )
        if not pth:
            return
        if not name:
            name = simpledialog.askstring('Model Name',
                'Install into which model?\n(leave blank to use file name)',
                parent=self.root) or ''
            name = name.strip().replace(' ', '_')
        pth = Path(pth)
        if not name:
            name = pth.stem
        dest = Path(__file__).parent / 'models' / name
        dest.mkdir(parents=True, exist_ok=True)
        shutil.copy(pth, dest / pth.name)
        cfg = pth.parent / 'config.json'
        if cfg.exists():
            shutil.copy(cfg, dest / 'config.json')
        self._tlog(f'✅ Installed  {pth.name}  →  models/{name}/')
        self.root.after(0, self._refresh_models)
        messagebox.showinfo('Model Installed',
            f'Trained model installed to models/{name}/\n\nSwitch to the Generate tab and select it!')

    def _run_manual_training(self):
        """Run the manual training script in a terminal."""
        import subprocess
        script = Path(__file__).parent / 'train_manual.sh'
        if not script.exists():
            messagebox.showerror('Script Not Found', 'train_manual.sh not found!')
            return
        
        # Open terminal and run the script
        try:
            # Try different terminal emulators
            term_cmds = [
                ['xterm', '-e', f'cd "{script.parent}" && bash "{script}"'],
                ['lxterminal', '-e', f'cd "{script.parent}" && bash "{script}"'],
                ['qterminal', '-e', f'cd "{script.parent}" && bash "{script}"'],
                ['konsole', '-e', f'cd "{script.parent}" && bash "{script}"'],
                ['gnome-terminal', '--', 'bash', '-c', f'cd "{script.parent}" && bash "{script}"'],
                ['xfce4-terminal', '-e', f'cd "{script.parent}" && bash "{script}"'],
            ]
            
            for cmd in term_cmds:
                try:
                    subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    self._tlog('🖥️  Manual training script launched in terminal')
                    return
                except FileNotFoundError:
                    continue
            
            # Fallback: just run in background
            subprocess.Popen(['bash', str(script)], cwd=str(script.parent))
            self._tlog('🖥️  Manual training script started')
            
        except Exception as e:
            messagebox.showerror('Error', f'Failed to start script: {e}')

    # ── CLOUD TRAINING STATUS MONITOR ─────────────────────────────────

    def _start_cloud_status_refresh(self):
        """Start auto-refreshing cloud training status every 30 seconds."""
        self._refresh_cloud_status()
        self._cloud_status_timer = self.root.after(30000, self._start_cloud_status_refresh)

    def _refresh_cloud_status(self):
        """Read the most recent cloud training log and update status display."""
        base = Path(__file__).parent
        candidates = [
            base / 'kaggle_training.log',
            base / 'training.log',
            base / 'training_watch.log',
        ]
        # Use most recently modified log file that exists
        existing = [(p.stat().st_mtime, p) for p in candidates if p.exists()]
        if not existing:
            status_text = 'No active cloud training.\nClick ☁️ CLOUD TRAIN to start training on Kaggle or Google Colab.'
            self._cloud_status_lbl.config(fg=C['gray'], text=status_text)
            return
        _, log_file = max(existing)
        
        try:
            with open(log_file, 'r') as f:
                lines = f.readlines()
            
            if not lines:
                status_text = 'Log file exists but is empty.\nTraining may be starting...'
                self._cloud_status_lbl.config(fg=C['orange'], text=status_text)
                return
            
            # Get last 15 lines for context
            recent_lines = lines[-15:]
            
            # Determine status
            full_log = ''.join(lines)
            
            if 'TRAINING COMPLETE' in full_log or '✅ TRAINING COMPLETE' in full_log:
                status_color = C['green']
                status_text = '🎉 TRAINING COMPLETE!\n\n'
                for line in reversed(lines):
                    if 'Model saved to:' in line or 'models/' in line:
                        status_text += f'Model: {line.strip()}\n'
                        break
                status_text += '\nClick 📥 INSTALL MODEL to import the trained model.'

            elif ('max_retries' in full_log or 'Max retries' in full_log or
                  'disk space' in full_log.lower() or 'KernelWorkerStatus.ERROR' in full_log):
                status_color = C['red']
                status_text = '❌ KAGGLE TRAINING FAILED\n\n'
                if 'disk space' in full_log.lower():
                    status_text += 'Cause: Kaggle ran out of disk space.\nFixed — click ☁️ CLOUD TRAIN to retry.\n'
                elif 'max_retries' in full_log or 'Max retries' in full_log:
                    status_text += 'Watcher hit max retries (10).\n'
                    for line in reversed(lines):
                        if 'error' in line.lower() or 'Error' in line:
                            status_text += f'{line.strip()}\n'; break
                status_text += '\nClick ☁️ CLOUD TRAIN → Kaggle to restart, or use Colab.'

            elif 'TRAINING FAILED' in full_log or '❌ TRAINING FAILED' in full_log:
                status_color = C['red']
                status_text = '❌ TRAINING FAILED\n\n'
                for line in reversed(lines):
                    if 'Error:' in line:
                        status_text += f'Error: {line.split("Error:", 1)[-1].strip()}\n'
                        break
                status_text += '\nClick ☁️ CLOUD TRAIN to try again or use Google Colab instead.'

            elif '⬆' in full_log or 'Uploading' in full_log:
                status_color = C['cyan']
                status_text = '⬆️ UPLOADING TO KAGGLE\n\n'
                for line in reversed(recent_lines):
                    if '%' in line or 'Zip:' in line:
                        status_text += f'Latest: {line.strip()}\n'
                        break
                status_text += '\nUploading training data to Kaggle (this may take 10-30 min for large datasets)...'

            elif 'Kaggle status:' in full_log or 'running' in full_log:
                status_color = C['cyan']
                status_text = '🚀 TRAINING ON KAGGLE GPU\n\n'
                for line in reversed(recent_lines):
                    if 'running' in line or 'elapsed' in line or 'Kaggle status:' in line:
                        status_text += f'{line.strip()}\n'
                        break
                status_text += '\nTraining in progress on Kaggle P100 GPU. This takes ~8-10 hours.'
                status_text += '\nYou can close this app — training runs in the cloud.'
                
            elif 'Packaging' in full_log or '📦' in full_log:
                status_color = C['orange']
                status_text = '📦 PACKAGING TRAINING DATA\n\n'
                for line in reversed(recent_lines):
                    if 'Zip:' in line or 'MB' in line:
                        status_text += f'{line.strip()}\n'
                        break
                status_text += '\nCompressing training data. This may take several minutes for large datasets...'
                
            else:
                status_color = C['gray']
                status_text = '⏳ INITIALIZING...\n\n'
                status_text += 'Latest log entries:\n'
                for line in recent_lines[-5:]:
                    status_text += f'  {line.strip()}\n'
            
            self._cloud_status_lbl.config(fg=status_color, text=status_text)
            
        except Exception as e:
            self._cloud_status_lbl.config(fg=C['red'], text=f'Error reading status: {e}')

    def _copy_log_path(self):
        """Copy the most recent log file path to clipboard."""
        base = Path(__file__).parent
        candidates = [base / 'kaggle_training.log', base / 'training.log', base / 'training_watch.log']
        existing = [(p.stat().st_mtime, p) for p in candidates if p.exists()]
        log_file = max(existing)[1] if existing else (base / 'kaggle_training.log')
        path_str = str(log_file)
        self.root.clipboard_clear()
        self.root.clipboard_append(path_str)
        self.root.update()
        messagebox.showinfo('Copied', f'Log path copied to clipboard:\n{path_str}')

    def _new_model_dlg(self):
        dlg=tk.Toplevel(self.root); dlg.title('New Model')
        dlg.configure(bg=C['bg2']); dlg.geometry('420x200')
        dlg.transient(self.root); dlg.grab_set()
        tk.Label(dlg,text='MODEL NAME',fg=C['cyan'],bg=C['bg2'],font=FONT['h2']).pack(pady=(20,8))
        nv=tk.StringVar()
        e=tk.Entry(dlg,textvariable=nv,bg=C['bg3'],fg=C['white'],
                   insertbackground=C['cyan'],font=FONT['body'],relief='flat',width=30)
        e.pack(ipady=8,pady=6); e.focus_set()
        def create():
            name=nv.get().strip().replace(' ','_')
            if name:
                (self.MODELS/name).mkdir(exist_ok=True)
                (self.DATASET/name).mkdir(exist_ok=True)
                self._refresh_models(); self.train_model_var.set(name)
                self._refresh_ds(); self._log(f'✅ Created: {name}'); dlg.destroy()
        NeonBtn(dlg,'CREATE',cmd=create,color=C['green'],w=160,h=42).pack(pady=10)
        e.bind('<Return>',lambda _:create())

    def _import_clip(self):
        m=self.train_model_var.get()
        if not m: messagebox.showwarning('No Model','Select target model.'); return
        p=filedialog.askopenfilename(title='Select Audio',
            filetypes=[('Audio','*.wav *.mp3 *.flac *.m4a *.ogg'),('All','*.*')])
        if p:
            self._separate_training_files(m, [Path(p)])

    def _import_ds_folder(self):
        m=self.train_model_var.get()
        if not m: messagebox.showwarning('No Model','Select target model.'); return
        folder=filedialog.askdirectory(title='Select Audio Folder')
        if folder:
            files = [fp for ext in ('*.wav','*.mp3','*.flac','*.m4a','*.ogg')
                     for fp in Path(folder).rglob(ext)]
            self._separate_training_files(m, files)

    def _separate_training_files(self, model_name, files):
        """Extract clean vocal stems before adding audio to an RVC dataset."""
        if not files:
            messagebox.showwarning('No Audio', 'No supported audio files found.')
            return

        def worker():
            from song_converter import separate_vocals
            dataset = self.DATASET / model_name
            work = self.OUTPUT / model_name / 'training_separation' / str(int(time.time()))
            dataset.mkdir(exist_ok=True)
            added = 0
            failures = []
            for index, source in enumerate(files, start=1):
                try:
                    self._prog(f'🎚 Separating {index}/{len(files)}: {source.name}',
                               int(index * 90 / len(files)))
                    vocal_path, _, method = separate_vocals(
                        source, work / str(index), method='demucs',
                        progress_cb=self._prog)
                    if not vocal_path or method != 'demucs':
                        raise RuntimeError('Demucs unavailable or separation failed')
                    destination = dataset / f'{source.stem}_vocals.wav'
                    shutil.copy2(vocal_path, destination)
                    added += 1
                except Exception as exc:
                    failures.append(f'{source.name}: {exc}')
            self._prog(f'✅ {added} vocal stem(s) ready for training', 100)
            self._log(f'🎤 Demucs training import: {added}/{len(files)} vocal stems')
            for failure in failures[:5]:
                self._log(f'⚠ {failure}')
            self.root.after(0, self._refresh_ds)

        threading.Thread(target=worker, daemon=True).start()

    def _open_ds_folder(self):
        m=self.train_model_var.get()
        t=(self.DATASET/m) if m else self.DATASET
        t.mkdir(exist_ok=True); self._open_dir(t)

    def _refresh_ds(self, _=None):
        self._ds_text.delete('1.0','end')
        m=self.train_model_var.get()
        dirs=[self.DATASET/m] if m else [d for d in self.DATASET.iterdir() if d.is_dir()]
        total=0
        for d in dirs:
            if not d.is_dir(): continue
            files=sorted([f for ext in ('.wav','.mp3','.flac','.m4a','.ogg')
                          for f in d.glob(f'*{ext}')])
            if not files: continue
            self._ds_text.insert('end',f'📁  {d.name}/   ({len(files)} files)\n')
            for fp in files[:30]:
                self._ds_text.insert('end',f'   ├  {fp.name}  ({fp.stat().st_size/1024:.1f}KB)\n')
            if len(files)>30:
                self._ds_text.insert('end',f'   └  …{len(files)-30} more\n')
            self._ds_text.insert('end','\n')
            total+=len(files)
        if total==0:
            self._ds_text.insert('end','No audio files yet.  Import some to get started.\n')

    def _analyze_voice(self):
        if not HAS_LIBROSA:
            messagebox.showwarning('Missing','pip install librosa'); return
        m=self.train_model_var.get()
        if not m: messagebox.showwarning('No Model','Select a model.'); return
        threading.Thread(target=self._analyze_worker,args=(m,),daemon=True).start()

    def _analyze_worker(self, name):
        self._prog('🔬 Analyzing voice…',10)
        d=self.DATASET/name
        if not d.exists(): self._log(f'❌ Not found: {d}'); return
        files=[f for ext in ('*.wav','*.mp3','*.flac') for f in d.glob(ext)]
        if not files: self._log('❌ No audio files'); return
        pitches,tempos,energies=[],[],[]
        for i,fp in enumerate(files[:10]):
            try:
                y,sr=librosa.load(str(fp),sr=22050,duration=30)
                pa,_=librosa.piptrack(y=y,sr=sr)
                p=pa[pa>50]
                if len(p): pitches.append(float(np.mean(p)))
                t,_=librosa.beat.beat_track(y=y,sr=sr)
                tempos.append(float(t))
                energies.append(float(np.mean(librosa.feature.rms(y=y)[0])))
                self._prog(f'Analyzing {i+1}/{min(10,len(files))}…',10+(i+1)*8)
            except Exception as e:
                self._log(f'⚠ {fp.name}: {e}')
        if pitches:
            profile={'speaker':name,'total_files':len(files),
                     'avg_pitch':float(np.mean(pitches)),
                     'pitch_range':[float(np.min(pitches)),float(np.max(pitches))],
                     'avg_tempo':float(np.mean(tempos)),
                     'avg_energy':float(np.mean(energies))}
            out=self.MODELS/name; out.mkdir(exist_ok=True)
            with open(out/'voice_profile.json','w') as f: json.dump(profile,f,indent=2)
            txt=(f'🎤 VOICE PROFILE: {name}\n{"═"*38}\n'
                 f'Avg Pitch : {profile["avg_pitch"]:.1f} Hz\n'
                 f'Range     : {profile["pitch_range"][0]:.0f}–{profile["pitch_range"][1]:.0f} Hz\n'
                 f'Avg Tempo : {profile["avg_tempo"]:.1f} BPM\n'
                 f'Energy    : {profile["avg_energy"]:.5f}\n'
                 f'Files     : {len(files)}\n\n'
                 f'Saved → models/{name}/voice_profile.json\n')
            self.root.after(0,lambda:(self._analysis_text.delete('1.0','end'),
                                      self._analysis_text.insert('1.0',txt)))
            self._log(f'✅ Analysis done: {name}')
        self._prog('✅ Done',100)

    # ═══════════════════════════════════════════════════════════════
    #  OUTPUTS LOGIC
    # ═══════════════════════════════════════════════════════════════
    def _refresh_outputs(self):
        for w in self._out_list_host.winfo_children(): w.destroy()
        all_files=[]
        if self.OUTPUT.exists():
            for d in sorted(self.OUTPUT.iterdir()):
                if d.is_dir():
                    for fp in sorted(d.glob('*.wav'),reverse=True):
                        all_files.append((d.name,fp))
                elif d.suffix=='.wav':
                    all_files.append(('root',d))
        if not all_files:
            tk.Label(self._out_list_host,text='No outputs yet.  Generate some vocals!',
                     fg=C['gray'],bg=C['bg'],font=FONT['body']).pack(pady=24)
            return
        cur=None
        for model,fp in all_files[:80]:
            if model!=cur:
                cur=model
                SectionHdr(self._out_list_host,f'📁  {model}/',C['orange'],C['bg'])
            self._out_row(fp)

    def _out_row(self, fp):
        c=AniCard(self._out_list_host, accent=C['orange'])
        c.pack(fill='x', padx=14, pady=3)
        inner=c.inner
        sz=fp.stat().st_size/1024
        tk.Label(inner,text=fp.name,fg=C['white'],bg=C['card2'],font=FONT['sm']).pack(side='left')
        tk.Label(inner,text=f'{sz:.1f}KB',fg=C['gray'],bg=C['card2'],font=FONT['sm']).pack(side='left',padx=(10,0))
        NeonBtn(inner,'▶',cmd=lambda f=fp:self._play_file(str(f)),color=C['green'],w=44,h=30).pack(side='right',padx=(6,0))
        NeonBtn(inner,'🗑',cmd=lambda f=fp:self._del_out(f),       color=C['red'],  w=44,h=30).pack(side='right',padx=(6,0))

    def _del_out(self,fp):
        if messagebox.askyesno('Delete',f'Delete {fp.name}?'):
            fp.unlink(); self._refresh_outputs()

    def _clear_all_outputs(self):
        if messagebox.askyesno('Clear All','Delete ALL output files?'):
            for item in self.OUTPUT.iterdir():
                if item.is_dir(): shutil.rmtree(item)
                elif item.suffix=='.wav': item.unlink()
            self._refresh_outputs(); self._log('🗑 All outputs cleared')

    # ─── UTILITIES ────────────────────────────────────────────────
    def _log(self, msg):
        def _do():
            self._out_log.insert('end',f'[{time.strftime("%H:%M:%S")}] {msg}\n')
            self._out_log.see('end')
        self.root.after(0,_do)

    def _prog(self, text, value):
        def _do():
            self.status_var.set(text)
            self._foot_bar.set(value)
        self.root.after(0,_do)

    def _open_dir(self, path):
        Path(path).mkdir(exist_ok=True)
        try:
            if sys.platform.startswith('linux'):
                subprocess.Popen(['xdg-open',str(path)])
            elif sys.platform=='darwin':
                subprocess.Popen(['open',str(path)])
            else:
                os.startfile(str(path))
        except Exception as e:
            self._log(f'❌ {e}')

# ═══════════════════════════════════════════════════════════════════
#  ENTRY POINT
# ═══════════════════════════════════════════════════════════════════
def main():
    root = tk.Tk()
    root.configure(bg=C['bg'])
    app = StudioPro(root)
    root.mainloop()

if __name__ == '__main__':
    main()
