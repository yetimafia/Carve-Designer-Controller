"""A minimal stand-in for tkinter so the designer's editing logic can run headless.
(The sandbox has no Tk; the real window is not exercised here, only the code behind it.)"""
import sys
import types
from unittest import mock


class TclError(Exception):
    pass


class Var:
    def __init__(self, master=None, value=None, **_):
        self._v = value

    def get(self):
        return self._v

    def set(self, v):
        self._v = v


class StringVar(Var):
    def __init__(self, master=None, value="", **kw):
        super().__init__(master, value)


class IntVar(Var):
    def __init__(self, master=None, value=0, **kw):
        super().__init__(master, value)


class BooleanVar(Var):
    def __init__(self, master=None, value=False, **kw):
        super().__init__(master, bool(value))


class FakeCanvas:
    def __init__(self, *a, **k):
        self.items, self._n = {}, 0

    def _new(self, kind, coords, opts):
        self._n += 1
        self.items[self._n] = dict(opts, kind=kind, coords=list(coords))
        return self._n

    def create_rectangle(self, x0, y0, x1, y1, **o):
        return self._new("rect", (x0, y0, x1, y1), o)

    def create_text(self, x, y, **o):
        return self._new("text", (x, y), o)

    def itemconfigure(self, i, **o):
        self.items[i].update(o)

    def coords(self, i, *c):
        self.items[i]["coords"] = list(c)

    def delete(self, *a):
        self.items.clear()

    def canvasx(self, v):
        return v

    def canvasy(self, v):
        return v

    def __getattr__(self, name):          # configure, bind, grid, tag_raise, xview ...
        return lambda *a, **k: None


class FakeText:
    instances = []

    def __init__(self, *a, **k):
        self.buf = ""
        FakeText.instances.append(self)

    def insert(self, idx, s):
        self.buf += s

    def delete(self, a, b=None):
        self.buf = ""

    def get(self, a, b=None):
        return self.buf + "\n"

    def __getattr__(self, name):
        return lambda *a, **k: None


def install():
    """Put fake tkinter / tkinter.ttk / filedialog / messagebox into sys.modules."""
    reg = types.SimpleNamespace(buttons={}, labels=[], dialogs=[], save_path=None, shown=[])

    def widget(*a, **k):
        return mock.MagicMock()

    def button(*a, **k):
        reg.buttons[k.get("text", "?")] = k.get("command")
        return mock.MagicMock()

    def label(*a, **k):
        m = mock.MagicMock()
        reg.labels.append(m)
        return m

    ttk = types.ModuleType("tkinter.ttk")
    for n in ("Frame", "Scrollbar", "Radiobutton", "Checkbutton", "Spinbox", "Entry", "Separator"):
        setattr(ttk, n, widget)
    ttk.Button, ttk.Label = button, label

    fd = types.ModuleType("tkinter.filedialog")
    fd.asksaveasfilename = lambda **k: reg.save_path
    fd.askopenfilename = lambda **k: reg.save_path

    mb = types.ModuleType("tkinter.messagebox")
    for n in ("showinfo", "showerror", "showwarning"):
        setattr(mb, n, lambda *a, _n=n, **k: reg.shown.append((_n, a)))

    tk = types.ModuleType("tkinter")
    tk.Tk = widget
    tk.Toplevel = widget
    tk.Canvas, tk.Text = FakeCanvas, FakeText
    tk.StringVar, tk.IntVar, tk.BooleanVar, tk.TclError = StringVar, IntVar, BooleanVar, TclError
    tk.ttk, tk.filedialog, tk.messagebox = ttk, fd, mb
    for name, mod in (("tkinter", tk), ("tkinter.ttk", ttk), ("tkinter.filedialog", fd),
                      ("tkinter.messagebox", mb)):
        sys.modules[name] = mod
    return reg
