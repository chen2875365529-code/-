# -*- coding: utf-8 -*-
"""
PromptFloat - 桌面悬浮提示词面板
自建提示词库 / 图文混排 / 置顶悬浮 / 全局热键
"""
import os, sys, io, json, time, uuid, ctypes, threading, traceback, queue
from ctypes import wintypes
import tkinter as tk
from tkinter import filedialog, messagebox
from PIL import Image, ImageTk, ImageGrab

APP_NAME = "PromptFloat"
BASE = os.path.join(os.environ.get("APPDATA") or os.path.expanduser("~"), APP_NAME)
IMG_DIR = os.path.join(BASE, "images")
DB_PATH = os.path.join(BASE, "prompts.json")
LOG_PATH = os.path.join(BASE, "error.log")

for d in (BASE, IMG_DIR):
    os.makedirs(d, exist_ok=True)


def enable_dpi_awareness():
    """开启 Per-Monitor DPI 感知，避免 125%/150% 缩放下界面被位图拉伸变糊"""
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
        return True
    except Exception:
        pass
    try:
        ctypes.windll.user32.SetProcessDPIAware()
        return True
    except Exception:
        return False


def primary_dpi():
    try:
        dc = ctypes.windll.user32.GetDC(0)
        dpi = ctypes.windll.gdi32.GetDeviceCaps(dc, 88)
        ctypes.windll.user32.ReleaseDC(0, dc)
        return int(dpi) if dpi else 96
    except Exception:
        return 96


DPI_AWARE = enable_dpi_awareness()
SCALE = max(1.0, primary_dpi() / 96.0)


def px(v):
    """逻辑尺寸 -> 物理像素"""
    return int(round(v * SCALE))

C_BG      = "#ffffff"
C_BG2     = "#f7f8fa"
C_CARD    = "#f4f5f7"
C_CARD_HI = "#e8f0fe"
C_BORDER  = "#e4e6ea"
C_TEXT    = "#16181d"
C_SUB     = "#6b7280"
C_ACCENT  = "#2f6feb"
C_DANGER  = "#d9483b"

FONT      = ("Microsoft YaHei UI", 10)
FONT_SM   = ("Microsoft YaHei UI", 9)
FONT_BOLD = ("Microsoft YaHei UI", 10, "bold")
FONT_TT   = ("Microsoft YaHei UI", 11, "bold")


def default_db():
    return {
        "version": 1,
        "window": {"x": None, "y": None, "w": None, "h": None, "collapsed": False, "alpha": 1.0},
        "prompts": [],
    }


def load_db():
    if not os.path.exists(DB_PATH):
        return default_db()
    try:
        with open(DB_PATH, "r", encoding="utf-8") as f:
            d = json.load(f) or {}
        base = default_db()
        base.update(d)
        base["window"] = {**default_db()["window"], **(d.get("window") or {})}
        base["prompts"] = d.get("prompts") or []
        return base
    except Exception:
        log_exc()
        return default_db()


def save_db(d):
    tmp = DB_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=2)
    os.replace(tmp, DB_PATH)


def log_exc():
    try:
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write("\n==== %s ====\n" % time.strftime("%Y-%m-%d %H:%M:%S"))
            f.write(traceback.format_exc())
    except Exception:
        pass


def new_prompt(title="", text="", tags=None, images=None):
    now = time.time()
    return {
        "id": uuid.uuid4().hex,
        "title": title or "未命名提示词",
        "text": text or "",
        "tags": tags or [],
        "images": images or [],
        "created": now,
        "updated": now,
        "pinned": False,
        "use_count": 0,
    }


user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

CF_UNICODETEXT, CF_DIB = 13, 8
GMEM_MOVEABLE = 0x0002

user32.OpenClipboard.argtypes = [wintypes.HWND]
user32.SetClipboardData.argtypes = [wintypes.UINT, wintypes.HANDLE]
user32.SetClipboardData.restype = wintypes.HANDLE
kernel32.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
kernel32.GlobalAlloc.restype = wintypes.HGLOBAL
kernel32.GlobalLock.argtypes = [wintypes.HGLOBAL]
kernel32.GlobalLock.restype = ctypes.c_void_p
kernel32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]


def _alloc_copy(data):
    h = kernel32.GlobalAlloc(GMEM_MOVEABLE, len(data))
    if not h:
        return None
    p = kernel32.GlobalLock(h)
    if not p:
        return None
    ctypes.memmove(p, data, len(data))
    kernel32.GlobalUnlock(h)
    return h


def clipboard_set(text=None, image=None):
    ok_open = False
    for _ in range(12):
        if user32.OpenClipboard(None):
            ok_open = True
            break
        time.sleep(0.03)
    if not ok_open:
        return False
    try:
        user32.EmptyClipboard()
        ok = False
        if image is not None:
            try:
                buf = io.BytesIO()
                im = image if image.mode == "RGB" else image.convert("RGB")
                im.save(buf, "BMP")
                h = _alloc_copy(buf.getvalue()[14:])
                if h:
                    user32.SetClipboardData(CF_DIB, h)
                    ok = True
            except Exception:
                log_exc()
        if text:
            h = _alloc_copy(text.encode("utf-16-le") + b"\x00\x00")
            if h:
                user32.SetClipboardData(CF_UNICODETEXT, h)
                ok = True
        return ok
    finally:
        user32.CloseClipboard()


def round_corners(hwnd, pref=2):
    try:
        dwm = ctypes.windll.dwmapi
        val = ctypes.c_int(pref)
        dwm.DwmSetWindowAttribute(wintypes.HWND(hwnd), 33, ctypes.byref(val), ctypes.sizeof(val))
    except Exception:
        pass

def dark_titlebar(hwnd, dark=True):
    try:
        dwm = ctypes.windll.dwmapi
        val = ctypes.c_int(1 if dark else 0)
        dwm.DwmSetWindowAttribute(wintypes.HWND(hwnd), 20, ctypes.byref(val), ctypes.sizeof(val))
    except Exception:
        pass


class ScrollFrame(tk.Frame):
    def __init__(self, master, bg=C_BG, **kw):
        super().__init__(master, bg=bg, **kw)
        self.canvas = tk.Canvas(self, bg=bg, bd=0, highlightthickness=0)
        self.vsb = tk.Scrollbar(self, orient="vertical", command=self.canvas.yview, width=8)
        self.inner = tk.Frame(self.canvas, bg=bg)
        self._win = self.canvas.create_window((0, 0), window=self.inner, anchor="nw")
        self.canvas.configure(yscrollcommand=self.vsb.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        self.vsb.pack(side="right", fill="y")
        self.inner.bind("<Configure>", self._on_inner)
        self.canvas.bind("<Configure>", self._on_canvas)
        self.canvas.bind("<Enter>", lambda e: self._bind_wheel(True))
        self.canvas.bind("<Leave>", lambda e: self._bind_wheel(False))
        self.inner.bind("<Enter>", lambda e: self._bind_wheel(True))

    def _on_inner(self, _=None):
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _on_canvas(self, e):
        self.canvas.itemconfigure(self._win, width=e.width)

    def _bind_wheel(self, on):
        if on:
            self.canvas.bind_all("<MouseWheel>", self._wheel)
        else:
            self.canvas.unbind_all("<MouseWheel>")

    def _wheel(self, e):
        try:
            if self.inner.winfo_reqheight() > self.canvas.winfo_height():
                self.canvas.yview_scroll(int(-1 * (e.delta / 120)), "units")
        except Exception:
            pass

    def to_top(self):
        self.canvas.yview_moveto(0)


class PromptCard(tk.Frame):
    def __init__(self, master, app, item, thumb):
        super().__init__(master, bg=C_CARD, highlightthickness=1,
                         highlightbackground=C_CARD, highlightcolor=C_CARD)
        self.app = app
        self.item = item
        self._hover = False
        self.configure(cursor="hand2")

        wrap = tk.Frame(self, bg=C_CARD)
        wrap.pack(fill="both", expand=True, padx=10, pady=9)
        kids = [wrap]

        if thumb is not None:
            left = tk.Frame(wrap, bg=C_CARD)
            left.pack(side="left", padx=(0, 10))
            lbl = tk.Label(left, image=thumb, bd=0, bg=C_CARD)
            lbl.image = thumb
            lbl.pack()
            lbl.bind("<Double-Button-1>", lambda e: (app.preview_images(item), "break")[1])
            lbl.configure(cursor="hand2")
            kids += [left, lbl]

        body = tk.Frame(wrap, bg=C_CARD)
        body.pack(side="left", fill="both", expand=True)

        head = tk.Frame(body, bg=C_CARD)
        head.pack(fill="x")
        pin = "[顶] " if item.get("pinned") else ""
        t = tk.Label(head, text=pin + (item.get("title") or "未命名"),
                     font=FONT_BOLD, fg=C_TEXT, bg=C_CARD, anchor="w")
        t.pack(side="left")
        if item.get("images"):
            ic = tk.Label(head, text="图 x%d" % len(item["images"]), font=("Microsoft YaHei UI", 8),
                          fg=C_SUB, bg=C_CARD)
            ic.pack(side="right")
            kids.append(ic)

        snippet = " ".join((item.get("text") or "").split())
        if len(snippet) > 88:
            snippet = snippet[:88] + "..."
        d = tk.Label(body, text=snippet or "(无正文)", font=FONT_SM, fg=C_SUB,
                     bg=C_CARD, anchor="w", justify="left", wraplength=px(280))
        d.pack(fill="x", pady=(3, 0))

        tags = item.get("tags") or []
        if tags:
            tg = tk.Label(body, text=" ".join("#" + x for x in tags[:5]),
                          font=("Microsoft YaHei UI", 8), fg=C_ACCENT, bg=C_CARD, anchor="w")
            tg.pack(fill="x", pady=(3, 0))
            kids.append(tg)

        kids += [body, head, t]
        self._kids = kids

        for w in self._kids + [self]:
            w.bind("<Enter>", self._enter)
            w.bind("<Leave>", self._leave)
            w.bind("<Button-1>", self._copy)
            w.bind("<Double-Button-1>", self._edit)
            w.bind("<Button-3>", self._menu)

    def _paint(self, bg):
        for w in self._kids:
            try:
                w.configure(bg=bg)
            except Exception:
                pass

    def _enter(self, _=None):
        if not self._hover:
            self._hover = True
            self._paint(C_CARD_HI)
            self.configure(highlightbackground="#c9d8f7", highlightcolor="#c9d8f7")

    def _leave(self, _=None):
        self._hover = False
        self._paint(C_CARD)
        self.configure(highlightbackground=C_CARD, highlightcolor=C_CARD)

    def _copy(self, _=None):
        self.app.copy_prompt(self.item)

    def _edit(self, _=None):
        self.app.edit_prompt(self.item)

    def _menu(self, e):
        m = tk.Menu(self, tearoff=0)
        m.add_command(label="复制提示词", command=lambda: self.app.copy_prompt(self.item))
        m.add_command(label="只复制图片", command=lambda: self.app.copy_image_only(self.item))
        m.add_command(label="查看大图", command=lambda: self.app.preview_images(self.item))
        m.add_separator()
        m.add_command(label="编辑", command=lambda: self.app.edit_prompt(self.item))
        m.add_command(label="取消置顶" if self.item.get("pinned") else "置顶",
                      command=lambda: self.app.toggle_pin(self.item))
        m.add_command(label="复制一份", command=lambda: self.app.duplicate_prompt(self.item))
        m.add_separator()
        m.add_command(label="删除", command=lambda: self.app.delete_prompt(self.item))
        m.tk_popup(e.x_root, e.y_root)


class PromptFloat:
    def __init__(self):
        self.db = load_db()
        self.q = queue.Queue()
        self.thumbs = {}
        self.expanded = False
        self._drag = None
        self._filter = ""

        self.root = tk.Tk()
        self.root.title(APP_NAME)
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.configure(bg=C_BG)
        icon = os.path.join(os.path.dirname(os.path.abspath(sys.argv[0])), "icon.ico")
        if os.path.exists(icon):
            try:
                self.root.iconbitmap(icon)
            except Exception:
                pass

        self._build_ball()
        self._build_panel()

        w = self.db["window"]
        self.panel_w = max(px(320), min(px(900), int(w.get("w") or px(420))))
        self.panel_h = max(px(260), min(px(1000), int(w.get("h") or px(580))))
        x, y = w.get("x"), w.get("y")
        if x is None or y is None:
            sw = self.root.winfo_screenwidth()
            x, y = sw - self.panel_w - 40, 90
        self.pos = [int(x), int(y)]

        self.root.geometry("%dx%d+%d+%d" % (self.panel_w, self.panel_h, self.pos[0], self.pos[1]))
        self.root.attributes("-alpha", float(w.get("alpha") or 1.0))
        self.root.after(80, self._apply_dwm)
        self.root.after(150, self._poll_hotkey)
        self._start_hotkey()
        self.root.protocol("WM_DELETE_WINDOW", self.quit)

        if self.db["window"].get("collapsed"):
            self.collapse()
        else:
            self.expand()

    def _hwnd(self):
        h = self.root.winfo_id()
        try:
            return ctypes.windll.user32.GetAncestor(h, 2) or h
        except Exception:
            return h

    def _apply_dwm(self):
        h = self._hwnd()
        round_corners(h, 2)
        dark_titlebar(h, False)

    def _build_ball(self):
        self.ball = tk.Frame(self.root, bg=C_BG)
        self.ball_cv = tk.Canvas(self.ball, width=px(56), height=px(56), bd=0,
                                 highlightthickness=0, bg=C_BG)
        self.ball_cv.pack()
        self._draw_ball()
        for w in (self.ball, self.ball_cv):
            w.bind("<Button-1>", self._ball_press)
            w.bind("<B1-Motion>", self._ball_drag)
            w.bind("<ButtonRelease-1>", self._ball_release)

    def _draw_ball(self, hot=False):
        c = self.ball_cv
        c.delete("all")
        c.create_oval(px(2), px(2), px(54), px(54), fill=(C_ACCENT if hot else "#1f2a44"), outline="")
        c.create_text(px(28), px(28), text="P", fill="white", font=("Microsoft YaHei UI", 17, "bold"))

    def _ball_press(self, e):
        self._drag = {"x": e.x_root, "y": e.y_root,
                      "wx": self.root.winfo_x(), "wy": self.root.winfo_y(), "moved": False}

    def _ball_drag(self, e):
        if not self._drag:
            return
        dx, dy = e.x_root - self._drag["x"], e.y_root - self._drag["y"]
        if abs(dx) > 3 or abs(dy) > 3:
            self._drag["moved"] = True
        self.pos = [self._drag["wx"] + dx, self._drag["wy"] + dy]
        self.root.geometry("+%d+%d" % (self.pos[0], self.pos[1]))

    def _ball_release(self, _=None):
        moved = self._drag and self._drag["moved"]
        self._drag = None
        if moved:
            self._save_win()
        else:
            self.expand()

    def _build_panel(self):
        self.panel = tk.Frame(self.root, bg=C_BG, highlightthickness=1,
                              highlightbackground=C_BORDER)

        bar = tk.Frame(self.panel, bg=C_BG, height=40)
        bar.pack(fill="x")
        bar.pack_propagate(False)

        logo = tk.Label(bar, text="P", bg=C_ACCENT, fg="white",
                        font=("Microsoft YaHei UI", 9, "bold"), width=3)
        logo.pack(side="left", padx=(10, 8), pady=8)
        title = tk.Label(bar, text="提示词面板", bg=C_BG, fg=C_TEXT, font=FONT_TT)
        title.pack(side="left")

        self._mini_btn(bar, "X", self.quit, C_DANGER).pack(side="right", padx=(0, 8))
        self._mini_btn(bar, "-", self.collapse, None).pack(side="right", padx=(0, 2))
        self._mini_btn(bar, "+", self.new_prompt, None).pack(side="right", padx=(0, 2))

        for w in (bar, logo, title):
            w.bind("<Button-1>", self._panel_press)
            w.bind("<B1-Motion>", self._panel_drag)

        sf = tk.Frame(self.panel, bg=C_BG2, highlightthickness=1, highlightbackground=C_BORDER)
        sf.pack(fill="x", padx=10, pady=(2, 8))
        tk.Label(sf, text="查找", bg=C_BG2, fg=C_SUB, font=FONT_SM).pack(side="left", padx=(8, 6))
        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", lambda *a: self._on_search())
        self.entry = tk.Entry(sf, textvariable=self.search_var, bd=0, bg=C_BG2,
                              fg=C_TEXT, insertbackground=C_TEXT, font=FONT)
        self.entry.pack(side="left", fill="x", expand=True, ipady=6, padx=(0, 6))
        tk.Label(sf, text="Ctrl+F", bg=C_BG2, fg="#a0a6b1",
                 font=("Microsoft YaHei UI", 8)).pack(side="right", padx=(0, 8))

        self.list_wrap = tk.Frame(self.panel, bg=C_BG)
        self.list_wrap.pack(fill="both", expand=True, padx=(6, 2))
        self.scroll = ScrollFrame(self.list_wrap, bg=C_BG)
        self.scroll.pack(fill="both", expand=True)

        foot = tk.Frame(self.panel, bg=C_BG, height=30)
        foot.pack(fill="x")
        foot.pack_propagate(False)
        self.status = tk.Label(foot, text="单击复制 / 双击编辑 / 右键更多",
                               bg=C_BG, fg=C_SUB, font=("Microsoft YaHei UI", 8), anchor="w")
        self.status.pack(side="left", padx=10)
        self.count_lbl = tk.Label(foot, text="", bg=C_BG, fg="#a0a6b1",
                                  font=("Microsoft YaHei UI", 8))
        self.count_lbl.pack(side="right", padx=10)

        self.grip = tk.Frame(self.panel, bg=C_BG, width=12, height=12, cursor="size_nw_se")
        self.grip.place(relx=1.0, rely=1.0, anchor="se")
        self.grip.bind("<Button-1>", self._grip_press)
        self.grip.bind("<B1-Motion>", self._grip_drag)

        self.root.bind("<Control-f>", lambda e: self.entry.focus_set())
        self.root.bind("<Control-n>", lambda e: self.new_prompt())
        self.root.bind("<Escape>", lambda e: self.collapse())

    def _mini_btn(self, parent, text, cmd, hover_color):
        b = tk.Label(parent, text=text, bg=C_BG, fg=C_SUB, font=("Microsoft YaHei UI", 10),
                     width=3, cursor="hand2")
        b.bind("<Button-1>", lambda e: cmd())
        b.bind("<Enter>", lambda e: b.configure(bg="#eceef2", fg=(hover_color or C_TEXT)))
        b.bind("<Leave>", lambda e: b.configure(bg=C_BG, fg=C_SUB))
        return b

    def _panel_press(self, e):
        self._drag = {"x": e.x_root, "y": e.y_root,
                      "wx": self.root.winfo_x(), "wy": self.root.winfo_y()}

    def _panel_drag(self, e):
        if not self._drag:
            return
        dx, dy = e.x_root - self._drag["x"], e.y_root - self._drag["y"]
        self.pos = [self._drag["wx"] + dx, self._drag["wy"] + dy]
        self.root.geometry("+%d+%d" % (self.pos[0], self.pos[1]))

    def _grip_press(self, e):
        self._gdrag = (e.x_root, e.y_root, self.root.winfo_width(), self.root.winfo_height())

    def _grip_drag(self, e):
        if not getattr(self, "_gdrag", None):
            return
        x0, y0, w0, h0 = self._gdrag
        w = max(px(320), min(px(900), w0 + (e.x_root - x0)))
        h = max(px(260), min(px(1000), h0 + (e.y_root - y0)))
        self.panel_w, self.panel_h = w, h
        self.root.geometry("%dx%d+%d+%d" % (w, h, self.pos[0], self.pos[1]))

    def expand(self):
        self.ball.pack_forget()
        self.panel.pack(fill="both", expand=True)
        self.expanded = True
        self.root.geometry("%dx%d+%d+%d" % (self.panel_w, self.panel_h,
                                            self.pos[0], self.pos[1]))
        self.root.attributes("-topmost", True)
        self.entry.focus_set()
        self.render_list()
        self._save_win()

    def collapse(self):
        self.panel.pack_forget()
        self.ball.pack()
        self.expanded = False
        self.root.geometry("%dx%d+%d+%d" % (px(56), px(56), self.pos[0], self.pos[1]))
        self._save_win()

    def toggle(self):
        if self.expanded:
            self.collapse()
        else:
            self.expand()

    def _save_win(self):
        w = self.db["window"]
        w["x"], w["y"] = self.pos[0], self.pos[1]
        if self.expanded:
            w["w"], w["h"] = self.panel_w, self.panel_h
        w["collapsed"] = not self.expanded
        if getattr(self, "_save_job", None):
            try:
                self.root.after_cancel(self._save_job)
            except Exception:
                pass
        self._save_job = self.root.after(400, lambda: save_db(self.db))

    def _start_hotkey(self):
        def worker():
            try:
                MOD_ALT, MOD_CONTROL, VK_P = 0x0001, 0x0002, 0x50
                if not user32.RegisterHotKey(None, 1, MOD_ALT | MOD_CONTROL, VK_P):
                    return
                msg = wintypes.MSG()
                while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) != 0:
                    if msg.message == 0x0312:
                        self.q.put("toggle")
            except Exception:
                pass
        threading.Thread(target=worker, daemon=True).start()

    def _poll_hotkey(self):
        try:
            while True:
                if self.q.get_nowait() == "toggle":
                    self.toggle()
        except queue.Empty:
            pass
        self.root.after(120, self._poll_hotkey)

    def _thumb_for(self, item):
        imgs = item.get("images") or []
        if not imgs:
            return None
        path = os.path.join(IMG_DIR, imgs[0])
        if not os.path.exists(path):
            return None
        key = (item["id"], imgs[0], os.path.getmtime(path))
        if key in self.thumbs:
            return self.thumbs[key]
        try:
            im = Image.open(path).convert("RGB")
            im.thumbnail((px(62), px(62)), Image.LANCZOS)
            ph = ImageTk.PhotoImage(im)
            self.thumbs[key] = ph
            return ph
        except Exception:
            log_exc()
            return None

    def _visible(self):
        q = self._filter.strip().lower()
        items = list(self.db["prompts"])
        if q:
            toks = q.split()

            def hit(it):
                blob = (it.get("title", "") + " " + it.get("text", "") + " " +
                        " ".join(it.get("tags") or [])).lower()
                return all(t in blob for t in toks)
            items = [x for x in items if hit(x)]
        items.sort(key=lambda x: (not x.get("pinned"), -(x.get("updated") or 0)))
        return items

    def render_list(self):
        for w in self.scroll.inner.winfo_children():
            w.destroy()
        items = self._visible()

        if not items:
            box = tk.Frame(self.scroll.inner, bg=C_BG)
            box.pack(fill="both", expand=True, pady=40)
            tk.Label(box, text="还没有提示词", bg=C_BG, fg=C_SUB, font=FONT).pack()
            tk.Label(box, text="点右上角 + 新建，支持文字 + 图片",
                     bg=C_BG, fg="#a0a6b1", font=FONT_SM).pack(pady=(6, 12))
            b = tk.Label(box, text="新建提示词", bg=C_ACCENT, fg="white",
                         font=FONT_SM, padx=14, pady=6, cursor="hand2")
            b.pack()
            b.bind("<Button-1>", lambda e: self.new_prompt())
        else:
            for it in items:
                PromptCard(self.scroll.inner, self, it, self._thumb_for(it)).pack(
                    fill="x", padx=4, pady=3)

        self.count_lbl.configure(text="%d / %d" % (len(items), len(self.db["prompts"])))
        self.scroll.to_top()

    def _on_search(self):
        self._filter = self.search_var.get()
        self.render_list()

    def _toast(self, text, ms=1400):
        self.status.configure(text=text, fg=C_ACCENT)
        if getattr(self, "_toast_job", None):
            try:
                self.root.after_cancel(self._toast_job)
            except Exception:
                pass
        self._toast_job = self.root.after(
            ms, lambda: self.status.configure(text="单击复制 / 双击编辑 / 右键更多", fg=C_SUB))

    def _first_image(self, item):
        for name in item.get("images") or []:
            path = os.path.join(IMG_DIR, name)
            if os.path.exists(path):
                try:
                    return Image.open(path).convert("RGB")
                except Exception:
                    log_exc()
        return None

    def copy_prompt(self, item):
        im = self._first_image(item)
        ok = clipboard_set(text=item.get("text") or item.get("title") or "", image=im)
        item["use_count"] = int(item.get("use_count") or 0) + 1
        item["updated"] = time.time()
        save_db(self.db)
        if ok:
            self._toast("已复制" + (" +图片" if im is not None else ""))
            self.render_list()
        else:
            self._toast("复制失败，剪贴板被占用", 2000)

    def copy_image_only(self, item):
        im = self._first_image(item)
        if im is None:
            self._toast("这条没有图片", 1600)
            return
        self._toast("已复制图片" if clipboard_set(text=None, image=im) else "复制失败", 1600)

    def toggle_pin(self, item):
        item["pinned"] = not item.get("pinned")
        item["updated"] = time.time()
        save_db(self.db)
        self.render_list()

    def preview_images(self, item):
        imgs = [n for n in (item.get("images") or [])
                if os.path.exists(os.path.join(IMG_DIR, n))]
        if not imgs:
            self._toast("这条没有图片", 1600)
            return
        win = tk.Toplevel(self.root)
        win.title("查看图片")
        win.configure(bg="#1b1d21")
        win.attributes("-topmost", True)
        win.geometry("%dx%d+%d+%d" % (px(760), px(560),
                                      self.pos[0] + px(40), self.pos[1] + px(40)))

        cv = tk.Canvas(win, bg="#1b1d21", bd=0, highlightthickness=0)
        cv.pack(fill="both", expand=True)
        state = {"i": 0, "photo": None}

        def fit(path):
            try:
                im = Image.open(path).convert("RGB")
            except Exception:
                log_exc()
                return None
            im.thumbnail((px(740), px(500)), Image.LANCZOS)
            return ImageTk.PhotoImage(im)

        def show(delta=0):
            state["i"] = (state["i"] + delta) % len(imgs)
            ph = fit(os.path.join(IMG_DIR, imgs[state["i"]]))
            cv.delete("all")
            if ph is None:
                return
            state["photo"] = ph
            cw = win.winfo_width() or px(760)
            chh = win.winfo_height() or px(560)
            cv.create_image(cw // 2, chh // 2, image=ph, anchor="center")
            cv.create_text(cw // 2, chh - px(14),
                           text="%d / %d     Left/Right 切换    Esc 关闭" % (state["i"] + 1, len(imgs)),
                           fill="#8b919c", font=FONT_SM)

        win.bind("<Left>", lambda e: show(-1))
        win.bind("<Right>", lambda e: show(1))
        win.bind("<Escape>", lambda e: win.destroy())
        win.bind("<Button-1>", lambda e: show(1))
        win.after(60, lambda: (show(0), win.focus_set()))

    def duplicate_prompt(self, item):
        cp = new_prompt(item.get("title", "") + " 副本", item.get("text", ""),
                        list(item.get("tags") or []), list(item.get("images") or []))
        self.db["prompts"].append(cp)
        save_db(self.db)
        self.render_list()

    def delete_prompt(self, item):
        if not messagebox.askyesno("删除", "确定删除「%s」？" % item.get("title", ""),
                                   parent=self.root):
            return
        self.db["prompts"] = [x for x in self.db["prompts"] if x["id"] != item["id"]]
        save_db(self.db)
        self.render_list()
        self._toast("已删除")

    def new_prompt(self):
        PromptEditor(self, None)

    def edit_prompt(self, item):
        PromptEditor(self, item)

    def quit(self):
        try:
            self._save_win()
            save_db(self.db)
        except Exception:
            log_exc()
        self.root.destroy()

    def run(self):
        self.root.mainloop()


def single_instance():
    k32 = ctypes.windll.kernel32
    k32.SetLastError(0)
    m = k32.CreateMutexW(None, False, "PromptFloat_SingleInstance_v1")
    return (m, k32.GetLastError() != 183)


class PromptEditor:
    def __init__(self, app, item):
        self.app = app
        self.is_new = item is None
        self.item = item or new_prompt()
        self.pending = list(self.item.get("images") or [])

        self.win = tk.Toplevel(app.root)
        self.win.title("新建提示词" if self.is_new else "编辑提示词")
        self.win.configure(bg=C_BG)
        self.win.geometry("%dx%d" % (px(560), px(640)))
        self.win.minsize(px(460), px(460))
        self.win.attributes("-topmost", True)
        self.win.transient(app.root)
        self.win.after(60, lambda: round_corners(
            ctypes.windll.user32.GetAncestor(self.win.winfo_id(), 2), 2))

        pad = 14
        tk.Label(self.win, text="标题", bg=C_BG, fg=C_SUB, font=FONT_SM).pack(
            anchor="w", padx=pad, pady=(12, 2))
        self.e_title = tk.Entry(self.win, font=FONT, bd=1, relief="solid")
        self.e_title.pack(fill="x", padx=pad, ipady=5)
        self.e_title.insert(0, self.item.get("title", ""))

        tk.Label(self.win, text="标签（逗号分隔）", bg=C_BG, fg=C_SUB, font=FONT_SM).pack(
            anchor="w", padx=pad, pady=(10, 2))
        self.e_tags = tk.Entry(self.win, font=FONT, bd=1, relief="solid")
        self.e_tags.pack(fill="x", padx=pad, ipady=5)
        self.e_tags.insert(0, ", ".join(self.item.get("tags") or []))

        tk.Label(self.win, text="正文", bg=C_BG, fg=C_SUB, font=FONT_SM).pack(
            anchor="w", padx=pad, pady=(10, 2))
        tw = tk.Frame(self.win, bd=1, relief="solid", bg=C_BG)
        tw.pack(fill="both", expand=True, padx=pad)
        self.t_text = tk.Text(tw, font=FONT, bd=0, wrap="word", undo=True,
                              bg=C_BG, fg=C_TEXT, insertbackground=C_TEXT,
                              padx=8, pady=6)
        vs = tk.Scrollbar(tw, command=self.t_text.yview, width=8)
        self.t_text.configure(yscrollcommand=vs.set)
        self.t_text.pack(side="left", fill="both", expand=True)
        vs.pack(side="right", fill="y")
        self.t_text.insert("1.0", self.item.get("text", ""))

        hdr = tk.Frame(self.win, bg=C_BG)
        hdr.pack(fill="x", padx=pad, pady=(10, 4))
        tk.Label(hdr, text="图片（可多张）", bg=C_BG, fg=C_SUB, font=FONT_SM).pack(side="left")

        add = tk.Label(hdr, text="+ 添加", bg=C_BG2, fg=C_TEXT, font=FONT_SM,
                       padx=8, pady=2, cursor="hand2")
        add.pack(side="right")
        add.bind("<Button-1>", lambda e: self.add_files())

        pas = tk.Label(hdr, text="粘贴", bg=C_BG2, fg=C_TEXT, font=FONT_SM,
                       padx=8, pady=2, cursor="hand2")
        pas.pack(side="right", padx=(0, 6))
        pas.bind("<Button-1>", lambda e: self.paste_image())

        self.strip = tk.Frame(self.win, bg=C_BG2, height=78)
        self.strip.pack(fill="x", padx=pad, pady=(0, 10))
        self.strip.pack_propagate(False)

        btns = tk.Frame(self.win, bg=C_BG)
        btns.pack(fill="x", padx=pad, pady=(0, 14))
        save = tk.Label(btns, text="保存", bg=C_ACCENT, fg="white",
                        font=FONT_SM, padx=20, pady=7, cursor="hand2")
        save.pack(side="right")
        save.bind("<Button-1>", lambda e: self.save())

        cancel = tk.Label(btns, text="取消", bg=C_BG2, fg=C_TEXT, font=FONT_SM,
                          padx=16, pady=7, cursor="hand2")
        cancel.pack(side="right", padx=(0, 8))
        cancel.bind("<Button-1>", lambda e: self.close())

        tk.Label(btns, text="Ctrl+S 保存", bg=C_BG, fg="#a0a6b1",
                 font=("Microsoft YaHei UI", 8)).pack(side="left")

        self.win.bind("<Control-s>", lambda e: self.save())
        self.win.bind("<Control-Return>", lambda e: self.save())
        self.win.bind("<Escape>", lambda e: self.close())
        self.e_title.focus_set()
        self.render_strip()

    def render_strip(self):
        for w in self.strip.winfo_children():
            w.destroy()
        if not self.pending:
            tk.Label(self.strip, text="暂无图片", bg=C_BG2, fg="#a0a6b1",
                     font=FONT_SM).pack(pady=27)
            return
        for idx, name in enumerate(self.pending):
            path = os.path.join(IMG_DIR, name)
            if not os.path.exists(path):
                continue
            try:
                im = Image.open(path).convert("RGB")
                im.thumbnail((px(62), px(62)), Image.LANCZOS)
                ph = ImageTk.PhotoImage(im)
            except Exception:
                continue
            cell = tk.Frame(self.strip, bg=C_BG2)
            cell.pack(side="left", padx=(8, 0), pady=7)
            lbl = tk.Label(cell, image=ph, bd=0, bg=C_BG2)
            lbl.image = ph
            lbl.pack()
            x = tk.Label(cell, text="x", bg="#333333", fg="white",
                         font=("Microsoft YaHei UI", 6), cursor="hand2")
            x.place(relx=1.0, rely=0.0, anchor="ne")
            x.bind("<Button-1>", lambda e, i=idx: self.remove_image(i))

    def add_files(self):
        files = filedialog.askopenfilenames(
            parent=self.win, title="选择图片",
            filetypes=[("图片", "*.png *.jpg *.jpeg *.webp *.bmp *.gif"), ("所有文件", "*.*")])
        for f in files:
            self._import_file(f)

    def _import_file(self, path):
        try:
            im = Image.open(path)
            im.load()
            name = uuid.uuid4().hex + ".png"
            dst = os.path.join(IMG_DIR, name)
            if im.mode in ("RGBA", "LA", "P"):
                im.convert("RGBA").save(dst, "PNG")
            else:
                im.convert("RGB").save(dst, "PNG")
            self.pending.append(name)
        except Exception:
            log_exc()
            messagebox.showerror("导入失败", "无法读取：%s" % os.path.basename(path),
                                 parent=self.win)
        self.render_strip()

    def paste_image(self):
        try:
            data = ImageGrab.grabclipboard()
        except Exception:
            data = None
        if isinstance(data, list):
            for f in data:
                if isinstance(f, str) and os.path.exists(f):
                    self._import_file(f)
            return
        if isinstance(data, Image.Image):
            name = uuid.uuid4().hex + ".png"
            data.convert("RGB").save(os.path.join(IMG_DIR, name), "PNG")
            self.pending.append(name)
            self.render_strip()
        else:
            messagebox.showinfo("提示", "剪贴板里没有图片", parent=self.win)

    def remove_image(self, idx):
        try:
            name = self.pending.pop(idx)
        except Exception:
            return
        used = any(name in (p.get("images") or []) for p in self.app.db["prompts"]
                   if p["id"] != self.item["id"])
        if not used:
            try:
                os.remove(os.path.join(IMG_DIR, name))
            except Exception:
                pass
        self.render_strip()

    def save(self):
        self.item["title"] = self.e_title.get().strip() or "未命名提示词"
        self.item["text"] = self.t_text.get("1.0", "end-1c")
        self.item["tags"] = [t.strip() for t in
                             self.e_tags.get().replace("，", ",").split(",") if t.strip()]
        self.item["images"] = self.pending
        self.item["updated"] = time.time()
        if self.is_new:
            self.app.db["prompts"].append(self.item)
        save_db(self.app.db)
        self.app.render_list()
        self.app._toast("已保存")
        self.close()

    def close(self):
        try:
            self.win.destroy()
        except Exception:
            pass


def main():
    try:
        handle, first = single_instance()
        if not first:
            return
        PromptFloat().run()
    except Exception:
        log_exc()
        try:
            messagebox.showerror("PromptFloat 启动失败",
                                 "错误已写入：\n%s" % LOG_PATH)
        except Exception:
            pass


if __name__ == "__main__":
    main()
