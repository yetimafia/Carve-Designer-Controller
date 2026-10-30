# GUI part: the main window, styling (apply_style) and the scrollable, resizable layout. The App class mixes in all the GUI parts.
# ====================================================================== GUI: main window
COL_BG = "#1e2227"


class App(ViewMixin, GitMixin, BlocksMixin, AutoMixin, FleetMixin):
    TOP = 28                    # room above the grid for the "FORWARD" label

    def __init__(self, root, cfg=None):
        self.root = root
        root.title("Carve Designer v" + VERSION)
        sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
        root.minsize(min(900, sw), min(600, sh))
        root.update_idletasks()
        if root.geometry().startswith("1x1"):                   # nobody sized the window yet: open it big, but inside the screen
            root.geometry("%dx%d" % (min(1360, int(sw * 0.88)), min(900, int(sh * 0.88))))
        self.apply_style()
        self.cfg = cfg if cfg is not None else load_config()
        load_texpack()
        TEX["mode"] = "imported" if (self.cfg.get("texture_mode") == "imported" and TEX["tiles"]) else "builtin"
        self.mode = "edit"                       # edit | preview | live
        self.design = Design()
        self.layer = 1
        # editing state
        self.undo = []
        self.items, self.cache = {}, {}
        self.cs = self.ox = self.oy = 0
        self.preview = {}
        self.unreachable = set()
        self.total = self.skipped = 0
        self.dragging = False
        self.paint_val = True
        self.start_cell = self.last_cell = None
        self._trail_cells = set()
        self._relayout_job = None
        # viewer state
        self.vdesign = self.view = self.sim = None
        self.play_idx = 0
        self.playing = False
        self._play_job = None
        self._scale_busy = False
        # live state
        self.server = None
        self.live_q = queue.Queue()
        self.sessions = {}
        self.live_current = None
        self.live_job = None
        # other
        self.dwin = None
        self.last_upload = None
        # tk variables
        c = self.cfg
        self.brush = None                        # slot painted cells will get, None = plain digging
        self.sel_slot = 16                       # slot picked in the inventory display
        self.item_var = tk.StringVar()
        self.brush_var = tk.StringVar(value="")
        self.supply_var = tk.StringVar(value="")
        self.torch_gap = tk.IntVar(value=4)
        self.pattern_var = tk.StringVar()
        self.torch_mode_var = tk.StringVar()
        self.marks, self.mcache = {}, {}
        self.tool = tk.StringVar(value="pencil")
        self.mark_name, self.mark_face = tk.StringVar(value="Tree farm"), tk.StringVar(value="forward")
        self._marks_sig = None
        self.hollow = tk.BooleanVar(value=False)
        self.chest_var = tk.BooleanVar(value=True)
        self.size_vars = [tk.IntVar(value=9), tk.IntVar(value=9), tk.IntVar(value=4)]
        self.name_var = tk.StringVar()
        self.follow_var = tk.BooleanVar(value=True)
        self.speed_var = tk.IntVar(value=6)
        self.seek_var = tk.DoubleVar(value=0)
        self.hover_var = tk.StringVar(value="")
        self.info_var = tk.StringVar(value="")
        self.stats_var = tk.StringVar(value="")
        self.gh_status = tk.StringVar(value="")
        self.dstatus = tk.StringVar(value="")
        self.live_status = tk.StringVar(value="Not listening.")
        self.repo_var = tk.StringVar(value=c.get("repo", ""))
        self.branch_var = tk.StringVar(value=c.get("branch", "main"))
        self.folder_var = tk.StringVar(value=c.get("folder", DEFAULT_FOLDER))
        self.token_var = tk.StringVar(value=c.get("token", "") or os.environ.get("GITHUB_TOKEN", ""))
        self.remember_var = tk.BooleanVar(value=bool(c.get("token")))
        self.live_enabled_var = tk.BooleanVar(value=bool(c.get("live_enabled", True)))
        self.seal_var = tk.BooleanVar(value=False)
        self.skin_var = tk.StringVar(value="Green turtle")
        self.share_var = tk.BooleanVar(value=bool(c.get("share", True)))
        self.share_url_var = tk.StringVar(value="")
        self.live_url_var = tk.StringVar(value=c.get("live_url", DEFAULT_LIVE_URL))
        self.lan_var = tk.BooleanVar(value=bool(c.get("lan", False)))
        self.build_ui()
        self.load_initial()
        root.protocol("WM_DELETE_WINDOW", self.on_close)

    # ------------------------------------------------------------------ plumbing
    def sd(self):
        """The design currently drawn (the real one, or the one being previewed / watched)."""
        return self.vdesign if (self.mode != "edit" and self.vdesign is not None) else self.design

    def info(self, title, msg):
        messagebox.showinfo(title, msg)

    def error(self, title, msg):
        messagebox.showerror(title, msg)

    def confirm(self, title, msg):
        return messagebox.askyesno(title, msg)

    def ask_save_path(self, **kw):
        return filedialog.asksaveasfilename(**kw)

    def ask_open_path(self, **kw):
        return filedialog.askopenfilename(**kw)

    def run_bg(self, fn, on_ok, on_err):
        """Run fn() on a worker thread; call on_ok(result) / on_err(exception) in the UI thread."""
        box = queue.Queue()

        def work():
            try:
                box.put((True, fn()))
            except Exception as ex:                       # shown to the user, never crashes the window
                box.put((False, ex))

        threading.Thread(target=work, daemon=True).start()

        def poll():
            try:
                ok, val = box.get_nowait()
            except queue.Empty:
                self.root.after(60, poll)
                return
            (on_ok if ok else on_err)(val)

        self.root.after(60, poll)

    # ------------------------------------------------------------------ look
    def apply_style(self):
        """One clean, flat look: soft grey panels, white fields, one blue accent, a readable system font."""
        import tkinter.font as tkfont
        root = self.root
        st = ttk.Style()
        try:
            st.theme_use("clam")
        except Exception:
            pass
        have = set(tkfont.families())
        family = next((f for f in ("Segoe UI", "SF Pro Text", "Helvetica Neue", "Inter", "Noto Sans", "DejaVu Sans", "Arial") if f in have), "TkDefaultFont")
        for name in ("TkDefaultFont", "TkTextFont", "TkMenuFont", "TkHeadingFont", "TkCaptionFont"):
            try:
                tkfont.nametofont(name).configure(family=family, size=10)
            except Exception:
                pass
        BG, CARD, FG, MUTED, LINE = "#f3f4f7", "#ffffff", "#1c2230", "#667085", "#d5d9e0"
        ACC, ACC_DK, BTN, BTN_HI = "#2f6fed", "#1f57c7", "#e7eaf0", "#dbe0e9"
        self.theme = {"bg": BG, "card": CARD, "fg": FG, "muted": MUTED, "line": LINE, "accent": ACC}
        root.configure(background=BG)
        root.option_add("*Listbox.background", CARD)
        root.option_add("*Listbox.relief", "flat")
        root.option_add("*Text.relief", "flat")
        root.option_add("*Menu.background", CARD)
        root.option_add("*Menu.foreground", FG)
        root.option_add("*Menu.activeBackground", ACC)
        root.option_add("*Menu.activeForeground", "#ffffff")
        st.configure(".", background=BG, foreground=FG, bordercolor=LINE, lightcolor=BG, darkcolor=BG, troughcolor="#e6e9ef",
                     focuscolor=ACC, selectbackground=ACC, selectforeground="#ffffff", insertcolor=FG)
        st.configure("TFrame", background=BG)
        st.configure("TLabel", background=BG, foreground=FG)
        st.configure("TButton", background=BTN, foreground=FG, padding=(14, 7), relief="flat", borderwidth=0, focusthickness=0)
        st.map("TButton", background=[("disabled", "#eceef2"), ("pressed", "#cfd5e0"), ("active", BTN_HI)],
               foreground=[("disabled", "#a3a9b5")])
        st.configure("Accent.TButton", background=ACC, foreground="#ffffff")
        st.map("Accent.TButton", background=[("pressed", ACC_DK), ("active", ACC_DK)])
        st.configure("Toolbutton", background=BTN, foreground=FG, padding=(16, 8), relief="flat", borderwidth=0)
        st.map("Toolbutton", background=[("selected", ACC), ("pressed", ACC_DK), ("active", BTN_HI)],
               foreground=[("selected", "#ffffff")])
        for kind in ("TCheckbutton", "TRadiobutton"):
            st.configure(kind, background=BG, foreground=FG, padding=2)
            st.map(kind, background=[("active", BG)], indicatorcolor=[("selected", ACC), ("!selected", CARD)])
        st.configure("TEntry", fieldbackground=CARD, foreground=FG, bordercolor=LINE, padding=4)
        st.map("TEntry", bordercolor=[("focus", ACC)])
        st.configure("TCombobox", fieldbackground=CARD, background=BTN, foreground=FG, bordercolor=LINE, arrowcolor=MUTED, padding=4)
        st.map("TCombobox", fieldbackground=[("readonly", CARD)], bordercolor=[("focus", ACC)], selectbackground=[("readonly", CARD)],
               selectforeground=[("readonly", FG)])
        st.configure("TSpinbox", fieldbackground=CARD, bordercolor=LINE, arrowcolor=MUTED, padding=3)
        st.configure("TNotebook", background=BG, borderwidth=0, tabmargins=(0, 4, 0, 0))
        st.configure("TNotebook.Tab", background=BG, foreground=MUTED, padding=(11, 8), borderwidth=0)
        st.map("TNotebook.Tab", background=[("selected", CARD), ("active", "#e9ecf2")], foreground=[("selected", ACC)])
        st.configure("TLabelframe", background=BG, bordercolor=LINE, relief="solid", borderwidth=1)
        st.configure("TLabelframe.Label", background=BG, foreground=MUTED, font=(family, 9, "bold"))
        st.configure("TScrollbar", background="#c9cfda", troughcolor=BG, bordercolor=BG, arrowcolor=MUTED, relief="flat", gripcount=0)
        st.map("TScrollbar", background=[("active", "#aeb6c4")])
        st.configure("TScale", background=BG, troughcolor="#dfe3ea")
        st.configure("Treeview", background=CARD, fieldbackground=CARD, foreground=FG, rowheight=24, borderwidth=0)
        st.map("Treeview", background=[("selected", ACC)], foreground=[("selected", "#ffffff")])
        st.configure("Treeview.Heading", background=BTN, foreground=FG, relief="flat", padding=(8, 5), font=(family, 9, "bold"))
        st.configure("TProgressbar", background=ACC, troughcolor="#e1e5ec", borderwidth=0)
        st.configure("TSeparator", background=LINE)
        st.configure("TPanedwindow", background=BG)

    # ------------------------------------------------------------------ layout
    def build_ui(self):
        r = self.root
        r.rowconfigure(0, weight=1)
        left = ttk.Frame(r)
        left.grid(row=0, column=0, sticky="nsew")
        left.columnconfigure(0, weight=1)
        left.rowconfigure(0, weight=1)
        self.canvas = tk.Canvas(left, bg=COL_BG, highlightthickness=0, width=640, height=600)
        self.canvas.grid(row=0, column=0, sticky="nsew")
        ttk.Label(left, textvariable=self.hover_var, anchor="w").grid(row=1, column=0, sticky="ew", padx=6, pady=2)

        self.left = left
        side = ttk.Frame(r, padding=(10, 8))
        side.grid(row=0, column=1, sticky="nsew")
        r.columnconfigure(0, weight=3)                          # the grid and the panel share extra room (set_mode shifts it)
        r.columnconfigure(1, weight=1)
        bar = ttk.Frame(side)
        bar.pack(fill="x", pady=(0, 6))
        self.mode_var = tk.StringVar(value="colony")
        for text, val in (("Colony (turtles)", "colony"), ("Carve by hand", "carve")):
            ttk.Radiobutton(bar, text=text, value=val, variable=self.mode_var, style="Toolbutton",
                            command=lambda: self.set_mode(self.mode_var.get())).pack(side="left", padx=(0, 4))
        row = self.design_row = ttk.Frame(side)
        row.pack(fill="x")
        ttk.Label(row, text="Design").pack(side="left")
        self.name_entry = ttk.Entry(row, textvariable=self.name_var, width=20)
        self.name_entry.pack(side="left", padx=4)
        self.name_entry.bind("<Return>", lambda e: self.commit_name())
        self.name_entry.bind("<FocusOut>", lambda e: self.commit_name())
        ttk.Button(row, text="New design", command=self.new_design).pack(side="left")
        ttk.Button(row, text="All designs...", command=self.open_designs_window).pack(side="left", padx=(3, 0))
        row = self.layer_row = ttk.Frame(side)
        row.pack(fill="x", pady=6)
        ttk.Label(row, text="Layer").pack(side="left")
        ttk.Button(row, text="\u2212", width=3, command=lambda: self.set_layer(self.layer - 1)).pack(side="left", padx=(6, 0))
        self.layer_lbl = ttk.Label(row, text="", width=8, anchor="center")
        self.layer_lbl.pack(side="left")
        ttk.Button(row, text="+", width=3, command=lambda: self.set_layer(self.layer + 1)).pack(side="left")
        ttk.Label(row, text="(wheel / PgUp / PgDn)", foreground="#666").pack(side="left", padx=6)

        nb = self.nb = ttk.Notebook(side)
        nb.pack(fill="both", expand=True)
        self.tabs = {}
        builders = (("Colony", self.build_colony_tab), ("Edit", self.build_edit_tab), ("Blocks", self.build_blocks_tab),
                    ("Preview / Live", self.build_view_tab), ("Automation", self.build_auto_tab), ("Fleet", self.build_fleet_tab),
                    ("GitHub", self.build_github_tab))
        self.tab_inner = {}
        for title, _b in builders:
            f = ttk.Frame(nb)
            nb.add(f, text=title)
            self.tabs[title] = f
            self.tab_inner[title] = self.make_scrollable(f)
        for title, build in sorted(builders, key=lambda b: b[0] == "Colony"):      # the colony tab needs the Fleet tab's server object
            build(self.tab_inner[title])

        self.nb_ready = True
        self.set_mode(self.cfg.get("mode") if self.cfg.get("mode") in ("colony", "carve") else "colony")

        c = self.canvas
        c.bind("<ButtonPress-1>", lambda e: self.on_press(e, False))
        c.bind("<B1-Motion>", self.on_motion)
        c.bind("<ButtonRelease-1>", self.on_release)
        for b in (2, 3):
            c.bind("<ButtonPress-%d>" % b, lambda e: self.on_press(e, True))
            c.bind("<B%d-Motion>" % b, self.on_motion)
            c.bind("<ButtonRelease-%d>" % b, self.on_release)
        c.bind("<Motion>", self.on_hover)
        c.bind("<MouseWheel>", self.on_wheel)
        c.bind("<Button-4>", lambda e: self.set_layer(self.layer + 1))
        c.bind("<Button-5>", lambda e: self.set_layer(self.layer - 1))
        c.bind("<Configure>", self.on_configure)
        r.bind("<Prior>", lambda e: self.set_layer(self.layer + 1))
        r.bind("<Next>", lambda e: self.set_layer(self.layer - 1))
        r.bind("<Control-z>", lambda e: self.do_undo())

    def make_scrollable(self, outer):
        """A frame inside `outer` that scrolls (scrollbar, mouse wheel) when the window is too small for its content."""
        canvas = tk.Canvas(outer, highlightthickness=0, borderwidth=0, width=330, height=300, background=self.theme["bg"])
        bar = ttk.Scrollbar(outer, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=bar.set)
        bar.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)
        inner = ttk.Frame(canvas, padding=8)
        win = canvas.create_window((0, 0), window=inner, anchor="nw")

        def on_inner(_e=None):
            canvas.configure(scrollregion=canvas.bbox("all"))
        inner.bind("<Configure>", on_inner)

        def fit():                                            # the panel is as wide as its widest widget needs (once, after it is built)
            kids = [c.winfo_reqwidth() for c in inner.winfo_children()]
            canvas.configure(width=min(480, max(300, (max(kids) if kids else 300) + 18)))
        outer.after(300, fit)
        wrap_job = [None]

        def rewrap(width):                                    # paragraphs follow the panel's width
            wrap_job[0] = None
            target = max(240, min(780, width - 70))

            def walk(w):
                for k in w.winfo_children():
                    if isinstance(k, (ttk.Label, tk.Label)):
                        try:
                            cur = int(float(str(k.cget("wraplength"))))
                        except (ValueError, tk.TclError):
                            cur = 0
                        if cur and not hasattr(k, "_wl0"):
                            k._wl0 = cur
                        if hasattr(k, "_wl0") and k._wl0 >= 280:
                            k.configure(wraplength=target)
                    walk(k)
            try:
                walk(inner)
            except tk.TclError:
                pass

        def on_canvas(e):                                     # the content is at most 820 px wide and centred in a wide window
            w = min(e.width, 820)
            canvas.itemconfigure(win, width=w)
            canvas.coords(win, max(0, (e.width - w) // 2), 0)
            if wrap_job[0] is not None:
                canvas.after_cancel(wrap_job[0])
            wrap_job[0] = canvas.after(90, lambda: rewrap(w))
        canvas.bind("<Configure>", on_canvas)

        def wheel(e):
            top, bottom = canvas.yview()
            if top <= 0 and bottom >= 1:
                return                                        # everything fits: nothing to scroll
            d = -1 if (getattr(e, "num", 0) == 4 or getattr(e, "delta", 0) > 0) else 1
            canvas.yview_scroll(d * 3, "units")
        for w in (canvas, inner):
            w.bind("<Enter>", lambda e: (outer.bind_all("<MouseWheel>", wheel), outer.bind_all("<Button-4>", wheel), outer.bind_all("<Button-5>", wheel)))
            w.bind("<Leave>", lambda e: None if str(outer.winfo_containing(e.x_root, e.y_root) or "").startswith(str(outer)) else
                   (outer.unbind_all("<MouseWheel>"), outer.unbind_all("<Button-4>"), outer.unbind_all("<Button-5>")))
        inner.scroll_canvas = canvas
        return inner

    def set_mode(self, mode):
        """Colony: only the turtle tabs (starter, Automation, Fleet, GitHub). Carve by hand: the design grid, layer controls and
        the Edit / Blocks / Preview tabs, hiding the colony starter."""
        if mode not in ("colony", "carve") or not getattr(self, "nb_ready", False):
            return
        self.mode_var.set(mode)
        carve_tabs = ("Edit", "Blocks", "Preview / Live")
        self.root.columnconfigure(0, weight=0 if mode == "colony" else 3)
        self.root.columnconfigure(1, weight=1)
        if mode == "colony":
            self.left.grid_remove()
            self.design_row.pack_forget()
            self.layer_row.pack_forget()
            for t in carve_tabs:
                self.nb.hide(self.tabs[t])
            self.nb.add(self.tabs["Colony"])
            self.nb.select(self.tabs["Colony"])
            if not getattr(self, "_colony_auto", False) and (self.token_var.get().strip() or os.environ.get("GITHUB_TOKEN")):
                self._colony_auto = True                  # automatic: put the five programs on GitHub the first time, if a token is saved
                self.root.after(400, self.colony_upload)
        else:
            self.left.grid()
            self.design_row.pack(fill="x", before=self.nb)
            self.layer_row.pack(fill="x", pady=6, before=self.nb)
            self.nb.hide(self.tabs["Colony"])
            for t in carve_tabs:
                self.nb.add(self.tabs[t])
            self.nb.select(self.tabs["Edit"])
        self.cfg["mode"] = mode
        try:
            save_config(self.cfg)
        except Exception:
            pass

    def build_edit_tab(self, p):
        bold = ("TkDefaultFont", 10, "bold")
        ttk.Label(p, text="Tool", font=bold).pack(anchor="w")
        for text, val in (("Pencil (drag to paint)", "pencil"), ("Rectangle", "rect"),
                          ("Ellipse", "ellipse"), ("Place turtle", "turtle"), ("Mark a station (base design)", "station")):
            ttk.Radiobutton(p, text=text, value=val, variable=self.tool).pack(anchor="w")
        mrow = ttk.Frame(p)
        mrow.pack(fill="x", pady=(0, 2))
        ttk.Label(mrow, text="  Station:").pack(side="left")
        self.mark_box = ttk.Combobox(mrow, textvariable=self.mark_name, width=16, values=self.station_names())
        self.mark_box.pack(side="left", padx=2)
        ttk.Combobox(mrow, textvariable=self.mark_face, values=list(MARK_FACES), state="readonly", width=7).pack(side="left")
        ttk.Label(p, foreground="#777", wraplength=300, justify="left", text=(
            "  Click a cell to say where that turtle's job starts (right-click removes). The turtle start cell T is the Foreman. "
            "The Colony tab can take every job's position from these marks.")).pack(anchor="w")
        ttk.Checkbutton(p, text="Hollow (outline only)", variable=self.hollow).pack(anchor="w", pady=(2, 0))
        ttk.Label(p, textvariable=self.brush_var, foreground="#b35c00").pack(anchor="w", pady=(0, 6))

        ttk.Label(p, text="Dig order", font=bold).pack(anchor="w")
        self.pattern_box = ttk.Combobox(p, textvariable=self.pattern_var, state="readonly", width=34,
                                        values=[label for _k, label in PATTERNS])
        self.pattern_box.pack(anchor="w", pady=(0, 6))
        self.pattern_box.bind("<<ComboboxSelected>>", lambda e: self.pick_pattern())

        ttk.Label(p, text="This layer", font=bold).pack(anchor="w")
        row = ttk.Frame(p)
        row.pack(fill="x")
        for text, op in (("Fill layer", "fill"), ("Clear layer", "clear"), ("Invert layer", "invert")):
            ttk.Button(row, text=text, command=lambda o=op: self.layer_op(o)).pack(side="left")
        row = ttk.Frame(p)
        row.pack(fill="x", pady=(2, 6))
        ttk.Button(row, text="Copy layer up", command=lambda: self.copy_layer(1)).pack(side="left")
        ttk.Button(row, text="Copy layer down", command=lambda: self.copy_layer(-1)).pack(side="left")

        ttk.Label(p, text="Shapes and templates", font=bold).pack(anchor="w")
        row = ttk.Frame(p)
        row.pack(fill="x", pady=(0, 6))
        ttk.Button(row, text="Shapes...", command=self.open_shapes).pack(side="left")
        ttk.Button(row, text="Templates...", command=self.open_templates).pack(side="left")
        ttk.Button(row, text="Import build...", command=self.import_schematic).pack(side="left")

        ttk.Label(p, text="Whole box", font=bold).pack(anchor="w")
        row = ttk.Frame(p)
        row.pack(fill="x", pady=(0, 6))
        ttk.Button(row, text="Fill whole box", command=lambda: self.all_op(True)).pack(side="left")
        ttk.Button(row, text="Clear whole box", command=lambda: self.all_op(False)).pack(side="left")

        ttk.Label(p, text="Size  (right x forward x up)", font=bold).pack(anchor="w")
        row = ttk.Frame(p)
        row.pack(fill="x", pady=(0, 6))
        for v in self.size_vars:
            ttk.Spinbox(row, from_=1, to=MAXDIM, width=4, textvariable=v).pack(side="left", padx=(0, 3))
        ttk.Button(row, text="Apply size", command=self.apply_size).pack(side="left", padx=3)

        ttk.Checkbutton(p, text="Chest directly behind turtle", variable=self.chest_var,
                        command=self.toggle_chest).pack(anchor="w")
        ttk.Checkbutton(p, text="Plug lava / water above and below (needs spare cobble)", variable=self.seal_var,
                        command=self.toggle_seal).pack(anchor="w", pady=(0, 6))
        ttk.Label(p, textvariable=self.stats_var, justify="left", wraplength=300).pack(anchor="w", pady=(0, 8))

        row = ttk.Frame(p)
        row.pack(fill="x")
        ttk.Button(row, text="Estimate...", command=self.open_estimate).pack(side="left")
        ttk.Button(row, text="Undo", command=self.do_undo).pack(side="left", padx=2)
        ttk.Button(row, text="Import design...", command=self.open_file).pack(side="left", padx=2)
        ttk.Button(row, text="Export design...", command=self.save_file).pack(side="left")

        ttk.Label(p, foreground="#666", justify="left", wraplength=330, text=(
            "Left-drag selects, right-drag erases. Orange = will be dug, red = not connected "
            "(skipped), green T = turtle, blue C = chest.")).pack(anchor="w", pady=(8, 0))

    # ------------------------------------------------------------------ loading / saving
    def load_initial(self):
        import_old_design()
        design = None
        last = self.cfg.get("last_design")
        if last:
            try:
                design = library_load(last)
            except Exception:
                design = None
        if design is None:
            for e in library_list():
                try:
                    design = library_load(e["slug"])
                    break
                except Exception:
                    continue
        if design is None:
            design = Design()
            design.name = "My first design"
        self.set_design(design)

    def set_design(self, design):
        self.design = design
        self.undo = []
        self.name_var.set(design.name)
        self.chest_var.set(design.chest)
        self.seal_var.set(design.seal)
        self.skin_var.set(dict(SKINS)[design.skin])
        for v, n in zip(self.size_vars, (design.w, design.d, design.h)):
            v.set(n)
        self.layer = max(1, min(design.h, design.ty))
        self.brush = None
        self.sel_slot = 16
        self.recompute()
        self.relayout(force=True)
        self.refresh_inventory()
        self.autosave()

    def autosave(self):
        try:
            library_save(self.design)
            self.cfg["last_design"] = self.design.slug()
            save_config(self.cfg)
        except OSError:
            pass

    def new_design(self):
        self.exit_view()
        self.commit_name()
        design = Design()
        design.name = unique_name("Untitled", {e["slug"] for e in library_list()})
        self.set_design(design)

    def commit_name(self):
        if self.mode != "edit":
            return
        old, new = self.design.name, clean_name(self.name_var.get())
        if new == old:
            self.name_var.set(new)
            return
        if slugify(new) != slugify(old) and slugify(new) in {e["slug"] for e in library_list()}:
            self.error("Name in use", "There is already a design called '%s' on this computer." % new)
            self.name_var.set(old)
            return
        if slugify(new) != slugify(old):
            library_delete(old)
        self.design.name = new
        self.name_var.set(new)
        self.after_edit()

    def open_file(self):
        path = self.ask_open_path(filetypes=[("Carve design", "*.json"), ("All files", "*.*")])
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                new = Design.from_json(json.load(f))
        except Exception as ex:
            self.error("Import", "Could not read that design:\n%s" % ex)
            return
        new.name = unique_name(new.name, {e["slug"] for e in library_list()})
        self.exit_view()
        self.set_design(new)

    def save_file(self):
        path = self.ask_save_path(defaultextension=".json", initialfile=self.design.slug() + ".json",
                                  filetypes=[("Carve design", "*.json")])
        if path:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(self.design.to_json(), f)

    def on_close(self):
        try:
            self.autosave()
            self.cfg["lan"] = bool(self.lan_var.get())
            save_config(self.cfg)
            self.stop_live()
        finally:
            self.root.destroy()

    # ------------------------------------------------------------------ canvas geometry
    def on_configure(self, _e):
        if self._relayout_job is None:
            self._relayout_job = self.root.after(30, self._do_relayout)

    def _do_relayout(self):
        self._relayout_job = None
        self.relayout()

    def fit(self):
        sd = self.sd()
        cw = self.canvas.winfo_width()
        ch = self.canvas.winfo_height()
        if cw < 60 or ch < 60:
            cw, ch = int(self.canvas.cget("width")), int(self.canvas.cget("height"))
        cs = int(max(8, min(44, (cw - 16) / sd.w, (ch - self.TOP - 12) / (sd.d + 1))))
        return cs, (cw - sd.w * cs) // 2, self.TOP, cw

    def relayout(self, force=False):
        cs, ox, oy, cw = self.fit()
        sd = self.sd()
        key = (cs, ox, oy, sd.w, sd.d)
        if force or key != getattr(self, "_built_key", None):
            self.cs, self.ox, self.oy, self.cw = cs, ox, oy, cw
            self._built_key = key
            self.build_canvas_items()
        self.refresh_layer()

    def cell_box(self, x, z):
        cs, d = self.cs, self.sd().d
        x0 = self.ox + (x - 1) * cs
        y0 = self.oy + (d - z) * cs
        return x0, y0, x0 + cs, y0 + cs

    def build_canvas_items(self):
        c, sd = self.canvas, self.sd()
        c.delete("all")
        self.items, self.cache = {}, {}
        self.marks, self.mcache = {}, {}
        for z in range(1, sd.d + 1):
            for x in range(1, sd.w + 1):
                self.items[(x, z)] = c.create_rectangle(*self.cell_box(x, z), fill="#000", outline="#20242a")
        font = ("TkDefaultFont", max(7, int(self.cs * 0.5)), "bold")
        self.top_label = c.create_text(self.cw // 2, 13, fill="#8b949e", text="", font=("TkDefaultFont", 10))
        self.turtle_txt = c.create_text(0, 0, text="T", fill="#102a06", state="hidden", font=font)
        self.chest_txt = c.create_text(0, 0, text="C", fill="#0b2a44", state="hidden", font=font)
        self.chest_box = c.create_rectangle(0, 0, 0, 0, fill="#4aa3df", outline="#20242a", state="hidden")
        self.chest_box_txt = c.create_text(0, 0, text="C", fill="#0b2a44", state="hidden", font=font)

    # ------------------------------------------------------------------ drawing
    def style_for(self, x, z):
        sd, y = self.sd(), self.layer
        alt = (x + z) % 2 == 0
        cell = (x, y, z)
        outline, width = "#20242a", 1
        if self.mode == "edit":
            if (x, y - 1, z) in sd.sel and cell not in sd.sel:
                outline, width = "#6fb1ff", 2
            if cell == sd.turtle:
                fill = self.skin_color(sd)
            elif (x, z) in self.preview:
                fill = "#ffe28a" if self.preview[(x, z)] else "#8a8f98"
            elif sd.chest and cell == sd.chest_cell:
                fill = "#4aa3df"
            elif cell in sd.sel:
                if cell in self.unreachable:
                    fill = "#d9534f" if alt else "#e57a77"
                else:
                    fill = "#f0a030" if alt else "#f6b653"
            else:
                fill = "#3b3f46" if alt else "#454a52"
            return fill, outline, width
        v = self.view
        if cell in self._trail_cells:
            outline, width = "#33d6ff", 2
        if v and cell == v.pos:
            fill = self.skin_color(sd)
        elif sd.chest and cell == sd.chest_cell:
            fill = "#4aa3df"
        elif v and cell in v.mined:
            fill = "#2e7d4f" if alt else "#348a58"                 # already dug
        elif cell in sd.sel:
            fill = ("#d9534f" if alt else "#e57a77") if cell in self.unreachable else ("#f0a030" if alt else "#f6b653")
        else:
            fill = "#3b3f46" if alt else "#454a52"
        return fill, outline, width

    def marker_for(self, x, z):
        """(colour, placed-already) for a cell that will receive a block, else None."""
        sd = self.sd()
        cell = (x, self.layer, z)
        slot = sd.place.get(cell)
        if slot is None or slot not in sd.inv:
            return None
        done = bool(self.view and self.mode != "edit" and cell in self.view.placed)
        return (item_color(sd.inv[slot]), done, sd.inv[slot])

    def draw_marker(self, x, z):
        mk = self.marker_for(x, z)
        tag = "mk%d_%d" % (x, z)
        if mk is None:
            if self.mcache.get((x, z)) is not None:
                self.canvas.delete(tag)
                self.mcache[(x, z)] = None
            return
        if self.mcache.get((x, z)) == (mk, self.cs):
            return
        self.canvas.delete(tag)
        x0, y0, x1, y1 = self.cell_box(x, z)
        bank = self.icon_bank() if self.cs >= 20 else None
        img = bank.get(mk[2], max(1, (int(self.cs) - 4) // 16)) if bank else None
        if img is not None:
            self.canvas.create_image((x0 + x1) / 2, (y0 + y1) / 2, image=img, tags=tag)
            if mk[1]:
                self.canvas.create_rectangle(x0 + 2, y0 + 2, x1 - 2, y1 - 2, outline="#3ddc84", width=2, tags=tag)
        else:
            inset = self.cs * (0.16 if mk[1] else 0.3)
            self.canvas.create_rectangle(x0 + inset, y0 + inset, x1 - inset, y1 - inset,
                                         fill=mk[0], outline="#101316", width=1, tags=tag)
        self.mcache[(x, z)] = (mk, self.cs)

    def refresh_cells(self, cells):
        for (x, z) in cells:
            item = self.items.get((x, z))
            if item is None:
                continue
            st = self.style_for(x, z)
            if self.cache.get(item) != st:
                self.canvas.itemconfigure(item, fill=st[0], outline=st[1], width=st[2])
                self.cache[item] = st
            self.draw_marker(x, z)

    def refresh_layer(self):
        sd, c, cs = self.sd(), self.canvas, self.cs
        if not self.items:
            return
        self._trail_cells = {t for t in self.view.trail if t[1] == self.layer} if self.view else set()
        self.refresh_cells(list(self.items.keys()))
        # turtle marker
        if self.mode == "edit":
            tcell, txt = sd.turtle, "T"
        else:
            tcell, txt = self.view.pos, ARROWS.get(self.view.face, "T")
        if tcell[1] == self.layer:
            x0, y0, x1, y1 = self.cell_box(tcell[0], tcell[2])
            c.coords(self.turtle_txt, (x0 + x1) / 2, (y0 + y1) / 2)
            c.itemconfigure(self.turtle_txt, text=txt, state="normal")
            c.tag_raise(self.turtle_txt)
        else:
            c.itemconfigure(self.turtle_txt, state="hidden")
        # chest marker: inside the grid, or just below it when the turtle is on the back row
        cc = sd.chest_cell
        if sd.chest and cc is not None and cc[1] == self.layer:
            x0, y0, x1, y1 = self.cell_box(cc[0], cc[2])
            c.coords(self.chest_txt, (x0 + x1) / 2, (y0 + y1) / 2)
            c.itemconfigure(self.chest_txt, state="normal")
            c.tag_raise(self.chest_txt)
        else:
            c.itemconfigure(self.chest_txt, state="hidden")
        if sd.chest and sd.tz == 1 and sd.ty == self.layer:
            x0 = self.ox + (sd.tx - 1) * cs
            y0 = self.oy + sd.d * cs + 3
            c.coords(self.chest_box, x0 + 2, y0, x0 + cs - 2, y0 + cs - 4)
            c.coords(self.chest_box_txt, x0 + cs / 2, y0 + (cs - 4) / 2)
            c.itemconfigure(self.chest_box, state="normal")
            c.itemconfigure(self.chest_box_txt, state="normal")
        else:
            c.itemconfigure(self.chest_box, state="hidden")
            c.itemconfigure(self.chest_box_txt, state="hidden")
        self.draw_marks()
        label = {"edit": "▲ FORWARD  (the turtle faces this way)",
                 "preview": "PREVIEW (simulated route)   ▲ forward",
                 "live": "LIVE – the real turtle   ▲ forward"}[self.mode]
        c.itemconfigure(self.top_label, text=label, fill="#8b949e" if self.mode == "edit" else "#33d6ff")
        self.layer_lbl.configure(text="%d / %d" % (self.layer, sd.h))
        if self.mode == "edit":
            places = len(build_place(sd))
            nbad = len(bad_torches(sd))
            self.stats_var.set("Selected: %d\nWill mine: %d\nUnreachable (skipped): %d\n"
                               "Fuel needed: up to ~%d%s" % (
                                   len(sd.sel), self.total, self.skipped, self.total,
                                   ("\nBlocks to place: %d" % places) if places else "")
                               + (("\nTorches that can't go in: %d (they need a dug cell above\nand a solid floor under them)" % nbad)
                                  if nbad else ""))

    def station_names(self):
        rows = getattr(self, "colony_rows", None)
        names = [r["job"]["name"] for r in rows] if rows else ["Foreman", "Storage keeper", "Tree farm", "Smelter", "Compressor", "Hauler"]
        return names

    def draw_marks(self):
        c = self.canvas
        c.delete("mark")
        sig = tuple(sorted(self.design.marks.items()))
        if sig != self._marks_sig:
            self._marks_sig = sig
            cb = getattr(self, "marks_changed", None)
            if cb:
                cb()
        if self.mode != "edit":
            return
        arrows = {"forward": "▲", "right": "▶", "back": "▼", "left": "◀"}
        for n, (x, y, z, f) in self.design.marks.items():
            if y != self.layer:
                continue
            x0, y0, x1, y1 = self.cell_box(x, z)
            c.create_rectangle(x0 + 1, y0 + 1, x1 - 1, y1 - 1, outline="#ff5ccb", width=2, tags="mark")
            c.create_text((x0 + x1) / 2, (y0 + y1) / 2, text=n[:1].upper() + arrows[f], fill="#ff9be0", tags="mark",
                          font=("TkDefaultFont", max(7, int(self.cs * 0.38)), "bold"))

    def recompute(self):
        run, self.total, self.skipped = build_run(self.design)
        d = self.design
        hidden = {d.chest_cell} if (d.chest and d.chest_cell) else set()
        self.unreachable = d.sel - run - hidden

    def after_edit(self):
        self.recompute()
        self.refresh_layer()
        self.refresh_inventory()
        self.autosave()

    # ------------------------------------------------------------------ editing
    def snapshot(self):
        self.undo.append(self.design.copy())
        if len(self.undo) > 60:
            self.undo.pop(0)

    def do_undo(self):
        if self.mode != "edit" or not self.undo:
            return
        old = self.undo.pop()
        resized = (old.w, old.d, old.h) != (self.design.w, self.design.d, self.design.h)
        old.name = self.design.name                   # names are not part of undo
        self.design = old
        self.chest_var.set(old.chest)
        self.seal_var.set(old.seal)
        self.skin_var.set(dict(SKINS)[old.skin])
        self.layer = max(1, min(self.layer, old.h))
        for v, n in zip(self.size_vars, (old.w, old.d, old.h)):
            v.set(n)
        self.recompute()
        self.relayout(force=resized)
        self.refresh_inventory()
        self.autosave()

    def set_layer(self, n):
        n = max(1, min(self.sd().h, n))
        if n != self.layer:
            self.layer = n
            self.refresh_layer()

    def on_wheel(self, e):
        self.set_layer(self.layer + (1 if e.delta > 0 else -1))

    def cell_at(self, e):
        sd = self.sd()
        if self.cs <= 0:
            return None
        x = int((e.x - self.ox) // self.cs) + 1
        row = int((e.y - self.oy) // self.cs)
        z = sd.d - row
        if 1 <= x <= sd.w and 1 <= z <= sd.d:
            return (x, z)
        return None

    def on_hover(self, e):
        cell = self.cell_at(e)
        self.hover_var.set("x %d   z %d   layer %d" % (cell[0], cell[1], self.layer) if cell else "")

    @staticmethod
    def line(a, b):
        (x0, z0), (x1, z1) = a, b
        n = max(abs(x1 - x0), abs(z1 - z0))
        if n == 0:
            return [a]
        return [(round(x0 + (x1 - x0) * i / n), round(z0 + (z1 - z0) * i / n)) for i in range(n + 1)]

    def paint(self, x, y, z, on):
        slot = self.brush if (on and self.brush in self.design.inv) else None
        self.design.set_cell(x, y, z, on, slot=slot)

    def on_press(self, e, erase):
        if self.mode != "edit":
            return
        cell = self.cell_at(e)
        if cell is None:
            return
        x, z = cell
        y, d = self.layer, self.design
        tool = self.tool.get()
        if tool == "station":
            self.snapshot()
            try:
                if erase:
                    for n in [n for n, m in d.marks.items() if m[:3] == (x, y, z)]:
                        del d.marks[n]
                else:
                    d.set_mark(self.mark_name.get(), x, y, z, self.mark_face.get())
            except ValueError as ex:
                self.hover_var.set(str(ex))
                return
            self.after_edit()
            return
        if tool == "turtle":
            self.snapshot()
            d.tx, d.ty, d.tz = x, y, z
            d.sel.discard(d.turtle)
            self.tool.set("pencil")
            self.after_edit()
            return
        self.snapshot()
        self.dragging = True
        want = (True, self.brush if self.brush in d.inv else None)
        self.paint_val = False if erase else d.cell_state((x, y, z)) != want
        self.start_cell = self.last_cell = cell
        if tool == "pencil":
            self.paint(x, y, z, self.paint_val)
            self.refresh_cells([cell])
        else:
            self.update_preview(cell)

    def on_motion(self, e):
        if not self.dragging or self.mode != "edit":
            return
        cell = self.cell_at(e)
        if cell is None or cell == self.last_cell:
            return
        if self.tool.get() == "pencil":
            touched = self.line(self.last_cell, cell)
            for (x, z) in touched:
                self.paint(x, self.layer, z, self.paint_val)
            self.refresh_cells(touched)
        else:
            self.update_preview(cell)
        self.last_cell = cell

    def shape_cells(self, a, b):
        (x0, z0), (x1, z1) = a, b
        xa, xb, za, zb = min(x0, x1), max(x0, x1), min(z0, z1), max(z0, z1)
        hollow = self.hollow.get()
        cells = set()
        if self.tool.get() == "rect":
            for x in range(xa, xb + 1):
                for z in range(za, zb + 1):
                    if hollow and xa < x < xb and za < z < zb:
                        continue
                    cells.add((x, z))
            return cells
        cx, cz = (xa + xb) / 2.0, (za + zb) / 2.0
        ra, rb = (xb - xa) / 2.0 + 0.5, (zb - za) / 2.0 + 0.5

        def inside(x, z, ra, rb):
            return ra > 0 and rb > 0 and ((x - cx) / ra) ** 2 + ((z - cz) / rb) ** 2 <= 1.0

        for x in range(xa, xb + 1):
            for z in range(za, zb + 1):
                if inside(x, z, ra, rb) and not (hollow and inside(x, z, ra - 1, rb - 1)):
                    cells.add((x, z))
        return cells

    def update_preview(self, cell):
        old = set(self.preview)
        self.preview = {c: self.paint_val for c in self.shape_cells(self.start_cell, cell)}
        self.refresh_cells(old | set(self.preview))

    def on_release(self, e):
        if not self.dragging:
            return
        self.dragging = False
        if self.preview:
            for (x, z) in self.preview:
                self.paint(x, self.layer, z, self.paint_val)
            self.preview = {}
        self.after_edit()

    def layer_op(self, op):
        if self.mode != "edit":
            return
        d, y = self.design, self.layer
        self.snapshot()
        for z in range(1, d.d + 1):
            for x in range(1, d.w + 1):
                if op == "fill":
                    self.paint(x, y, z, True)
                elif op == "clear":
                    d.set_cell(x, y, z, False)
                else:
                    self.paint(x, y, z, (x, y, z) not in d.sel)
        self.after_edit()

    def copy_layer(self, step):
        d, y = self.design, self.layer
        to = y + step
        if self.mode != "edit" or not 1 <= to <= d.h:
            return
        self.snapshot()
        for z in range(1, d.d + 1):
            for x in range(1, d.w + 1):
                d.set_cell(x, to, z, (x, y, z) in d.sel, slot=d.place.get((x, y, z)))
        self.layer = to
        self.after_edit()

    def all_op(self, on):
        if self.mode != "edit":
            return
        d = self.design
        self.snapshot()
        for y in range(1, d.h + 1):
            for z in range(1, d.d + 1):
                for x in range(1, d.w + 1):
                    self.paint(x, y, z, on)
        self.after_edit()

    def apply_size(self):
        if self.mode != "edit":
            return
        try:
            w, dd, h = (int(v.get()) for v in self.size_vars)
        except (tk.TclError, ValueError):
            self.error("Size", "Enter whole numbers for the size.")
            return
        if not all(1 <= n <= MAXDIM for n in (w, dd, h)):
            self.error("Size", "Each size must be between 1 and %d." % MAXDIM)
            return
        self.snapshot()
        self.design.resize(w, dd, h)
        self.layer = max(1, min(self.layer, h))
        self.recompute()
        self.relayout(force=True)
        self.refresh_inventory()
        self.autosave()

    def open_estimate(self):
        """Fuel, time and how many stacks of each block the job needs - from the exact route."""
        if self.mode != "edit":
            return
        self.commit_name()
        design = self.design.copy()
        if build_run(design)[1] == 0:
            self.info("Estimate", "Select some cells connected to the turtle first.")
            return
        self.stats_var.set("Working out the estimate...")

        def work():
            return estimate(design)

        def done(est):
            self.recompute()
            self.refresh_layer()
            top = tk.Toplevel(self.root)
            top.title("Estimate - " + design.name)
            top.transient(self.root)
            f = ttk.Frame(top, padding=12)
            f.pack(fill="both", expand=True)
            txt = tk.Text(f, width=64, height=min(24, 6 + len(est["lines"]) + 3 * len(est["warnings"])), wrap="word")
            txt.pack(fill="both", expand=True)
            txt.insert("1.0", estimate_text(est))
            txt.configure(state="disabled")
            ttk.Button(f, text="Close", command=top.destroy).pack(anchor="e", pady=(8, 0))
            self.estimate_window = top
            self.last_estimate = est
        self.run_bg(work, done, lambda ex: self.error("Estimate", str(ex)))

    def import_schematic(self, path=None):
        """Turn a Litematica / WorldEdit / structure-block file into a dig-and-place design."""
        if self.mode != "edit":
            return
        path = path or self.ask_open_path(filetypes=[("Minecraft builds", "*.litematic *.schem *.nbt"),
                                                      ("All files", "*.*")])
        if not path:
            return
        try:
            des, rep = schematic_design(load_schematic(path),
                                        name=clean_name(os.path.splitext(os.path.basename(path))[0]) or "Imported build")
        except SchematicError as ex:
            self.error("Import build", str(ex))
            return
        self.exit_view()
        self.commit_name()
        des.name = unique_name(des.name, {e["slug"] for e in library_list()})
        self.set_design(des)
        msg = "Imported %d blocks (%d x %d x %d), %d kinds." % ((rep["blocks"],) + tuple(rep["size"]) + (rep["kinds"],))
        if rep["mapped"]:
            msg += " The turtle holds 8 kinds, so %d rarer ones became the most similar of the 8." % rep["mapped"]
        if rep["unreachable"]:
            msg += " %d blocks float apart from the rest and will be skipped." % rep["unreachable"]
        self.info("Import build", msg)
        return rep

    def open_shapes(self):
        if self.mode != "edit":
            return
        top = tk.Toplevel(self.root)
        top.title("Shapes")
        top.transient(self.root)
        f = ttk.Frame(top, padding=12)
        f.pack(fill="both", expand=True)
        d = self.design
        ttk.Label(f, text="Fills the whole box (%d x %d x %d). Change the size first if you want it bigger."
                  % (d.w, d.d, d.h), wraplength=360).pack(anchor="w", pady=(0, 8))
        kind = tk.StringVar(value="cylinder")
        for key, label in SHAPES:
            ttk.Radiobutton(f, text=label, value=key, variable=kind).pack(anchor="w")
        hollow = tk.BooleanVar(value=False)
        caps = tk.BooleanVar(value=True)
        repl = tk.BooleanVar(value=True)
        ttk.Checkbutton(f, text="Hollow (only the outer skin)", variable=hollow).pack(anchor="w", pady=(8, 0))
        ttk.Checkbutton(f, text="...with floor and ceiling", variable=caps).pack(anchor="w", padx=(18, 0))
        ttk.Checkbutton(f, text="Replace what is there now", variable=repl).pack(anchor="w", pady=(4, 0))
        note = ("The selected block (if any) is placed in every cell." if self.brush in d.inv
                else "Tip: pick a block on the Blocks tab first to build the shape out of it.")
        ttk.Label(f, text=note, foreground="#666", wraplength=360).pack(anchor="w", pady=(6, 8))

        def go():
            cells = shape_cells(kind.get(), d.w, d.d, d.h, hollow.get(), caps.get())
            self.snapshot()
            apply_cells(self.design, cells, replace=repl.get(),
                        slot=self.brush if self.brush in self.design.inv else None)
            self.layer = max(1, min(self.design.h, self.design.ty))
            self.recompute()
            self.relayout(force=True)
            self.after_edit()
            top.destroy()
        row = ttk.Frame(f)
        row.pack(fill="x")
        ttk.Button(row, text="Apply", command=go).pack(side="left")
        ttk.Button(row, text="Close", command=top.destroy).pack(side="left", padx=4)
        self.shapes_dialog = top

    def open_templates(self):
        if self.mode != "edit":
            return
        top = tk.Toplevel(self.root)
        top.title("Templates")
        top.transient(self.root)
        f = ttk.Frame(top, padding=12)
        f.pack(fill="both", expand=True)
        ttk.Label(f, text="Start a new design from a ready-made one.", wraplength=360).pack(anchor="w", pady=(0, 8))

        def make(key):
            top.destroy()
            self.exit_view()
            self.commit_name()
            design = template_design(key)
            design.name = unique_name(design.name, {e["slug"] for e in library_list()})
            self.set_design(design)
        for key, title, blurb, (w, dd, h), _fn in TEMPLATES:
            row = ttk.Frame(f)
            row.pack(fill="x", pady=2)
            ttk.Button(row, text=title, width=30, command=lambda k=key: make(k)).pack(side="left")
            ttk.Label(row, text="%dx%dx%d  %s" % (w, dd, h, blurb), foreground="#666").pack(side="left", padx=6)
        self.templates_dialog = top

    def toggle_seal(self):
        if self.mode != "edit":
            self.seal_var.set(self.design.seal)
            return
        self.snapshot()
        self.design.seal = bool(self.seal_var.get())
        self.autosave()

    def toggle_chest(self):
        if self.mode != "edit":
            self.chest_var.set(self.design.chest)
            return
        self.snapshot()
        self.design.chest = self.chest_var.get()
        self.after_edit()


def main():
    if not TK_OK:
        print("This program needs Python with tkinter (included with the python.org installers;\n"
              "on Linux install the python3-tk package).")
        sys.exit(1)
    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
