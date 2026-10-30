# GUI part: the turtle inventory ('Blocks') tab and the item picture bank used by every tab.
# ============================================================ GUI: turtle inventory ("Blocks" tab)
class IconBank:
    """Pictures of vanilla items, drawn from our own simplified tiles (see item_tile). Anything it does not
    know (modded items) gets None, and the caller draws a coloured square instead."""

    def __init__(self, root):
        self.root = root
        self.cache = {}

    def known(self, item):
        return display_tile(item) is not None

    def names(self):
        names = set(icon_names())
        if TEX["mode"] == "imported":
            names |= set(pack_names())
        return sorted(names)

    def get(self, item, zoom=1):
        key = (item, zoom)
        if key in self.cache:
            return self.cache[key]
        tile = display_tile(item)
        if tile is None:
            return None
        img = tk.PhotoImage(master=self.root, width=16, height=16)
        for y, row in enumerate(tile):
            img.put("{" + " ".join("#%02x%02x%02x" % c if c else "#000000" for c in row) + "}", to=(0, y))
            for x, c in enumerate(row):
                if c is None:
                    img.transparency_set(x, y, True)
        if zoom > 1:
            big = tk.PhotoImage(master=self.root, width=16 * zoom, height=16 * zoom)
            big.tk.call(str(big), "copy", str(img), "-zoom", zoom, zoom)
            img = big
        self.cache[key] = img
        return img

    def swatch(self, item, size=16):
        key = ("sw", item, size)
        img = self.cache.get(key)
        if img is None:
            img = tk.PhotoImage(master=self.root, width=size, height=size)
            img.put("#101316", to=(0, 0, size, size))
            img.put(display_color(item), to=(1, 1, size - 1, size - 1))
            self.cache[key] = img
        return img

    def picture(self, item, zoom=1):
        return self.get(item, zoom) or self.swatch(item, 16 * zoom)


class BlocksMixin:
    """A little picture of the turtle's 16 slots. A slot with an item is reserved for placing:
    the turtle keeps that item there. Paint cells with a slot as the brush to make the turtle dig
    them out and then put that item in; torches can be spread over the floor automatically."""

    SLOT_PX = 62

    def icon_bank(self):
        if not hasattr(self, "_icons"):
            try:
                self._icons = IconBank(self.root)
            except Exception:
                self._icons = None          # no PNG support: coloured squares only
        return self._icons

    def build_blocks_tab(self, p):
        bold = ("TkDefaultFont", 10, "bold")
        ttk.Label(p, text="Turtle inventory", font=bold).pack(anchor="w")
        px = self.SLOT_PX
        self.inv_canvas = tk.Canvas(p, width=px * 4, height=px * 4, bg="#14171a", highlightthickness=0)
        self.inv_canvas.pack(anchor="w", pady=(2, 4))
        self.inv_canvas.bind("<ButtonPress-1>", self.inv_click)
        self.inv_canvas.bind("<Double-Button-1>", self.inv_double)
        ttk.Label(p, foreground="#666", wraplength=300, justify="left", text=(
            "Click a slot, then pick its item. A slot with an item is kept for placing "
            "(never dumped or burnt); empty slots hold what it digs up and its fuel."
        )).pack(anchor="w")

        self.slot_title = ttk.Label(p, text="", font=bold)
        self.slot_title.pack(anchor="w", pady=(6, 2))
        row = ttk.Frame(p)
        row.pack(fill="x")
        self.item_box = ttk.Combobox(row, textvariable=self.item_var, width=24,
                                     values=[n for n, _c in ITEM_PRESETS])
        self.item_box.pack(side="left")
        self.item_box.bind("<Return>", lambda e: self.set_slot_from_box())
        self.item_box.bind("<<ComboboxSelected>>", lambda e: self.set_slot_from_box())
        ttk.Button(row, text="Browse items...", command=self.open_picker).pack(side="left", padx=(6, 0))
        ttk.Button(row, text="Textures...", command=self.open_textures).pack(side="left", padx=(4, 0))
        row = ttk.Frame(p)
        row.pack(fill="x", pady=3)
        ttk.Button(row, text="Empty slot", command=self.empty_slot).pack(side="left")
        self.fav_btn = ttk.Button(row, text="Add to favorites", command=self.toggle_slot_favorite)
        self.fav_btn.pack(side="left", padx=4)
        ttk.Button(row, text="Paint with this", command=self.use_brush).pack(side="left")

        self.fav_title = ttk.Label(p, text="Favorites", font=bold)
        self.fav_title.pack(anchor="w", pady=(4, 1))
        self.fav_bar = ttk.Frame(p)
        self.fav_bar.pack(anchor="w", fill="x")
        self.fav_hint = tk.StringVar(value="")
        ttk.Label(p, textvariable=self.fav_hint, foreground="#666").pack(anchor="w")

        ttk.Label(p, textvariable=self.brush_var, foreground="#b35c00").pack(anchor="w", pady=(4, 0))
        ttk.Button(p, text="Back to plain digging", command=self.dig_only).pack(anchor="w", pady=(2, 6))

        ttk.Label(p, text="Torches", font=bold).pack(anchor="w")
        self.torch_box = ttk.Combobox(p, textvariable=self.torch_mode_var, state="readonly", width=34,
                                      values=[label for _k, label in TORCH_MODES])
        self.torch_box.pack(anchor="w", pady=(2, 0))
        self.torch_box.bind("<<ComboboxSelected>>", lambda e: self.pick_torch_mode())
        row = ttk.Frame(p)
        row.pack(fill="x", pady=2)
        ttk.Label(row, text="one every").pack(side="left")
        ttk.Spinbox(row, from_=1, to=16, width=3, textvariable=self.torch_gap).pack(side="left", padx=3)
        ttk.Label(row, text="cells on the floor").pack(side="left")
        row = ttk.Frame(p)
        row.pack(fill="x", pady=2)
        ttk.Button(row, text="Add torches", command=self.add_torches).pack(side="left")
        ttk.Button(row, text="Remove all placed blocks", command=self.clear_all_blocks).pack(side="left", padx=4)

        ttk.Label(p, textvariable=self.supply_var, justify="left", wraplength=300).pack(anchor="w", pady=(6, 0))

    # ------------------------------------------------------------------ drawing the slots
    def refresh_inventory(self):
        c = getattr(self, "inv_canvas", None)
        if c is None:
            return
        d = self.design
        if self.brush is not None and self.brush not in d.inv:
            self.brush = None
        need = supply_needs(d)
        c.delete("all")
        px = self.SLOT_PX
        for s in range(1, 17):
            col, row = (s - 1) % 4, (s - 1) // 4
            x0, y0 = col * px, row * px
            name = d.inv.get(s)
            c.create_rectangle(x0 + 2, y0 + 2, x0 + px - 2, y0 + px - 2,
                               fill="#2b3038" if name else "#1b1f24", outline="#3d444d")
            c.create_text(x0 + 7, y0 + 8, text=str(s), anchor="w", fill="#8b949e", font=("TkDefaultFont", 8))
            if name:
                bank = self.icon_bank()
                img = bank.get(name, 2) if bank else None
                if img is not None:
                    c.create_image(x0 + px // 2, y0 + 30, image=img)
                else:
                    c.create_rectangle(x0 + 19, y0 + 15, x0 + px - 19, y0 + px - 25,
                                       fill=item_color(name), outline="#0e1114")
                short = item_label(name)
                c.create_text(x0 + px / 2, y0 + px - 15, text=short[:10], fill="#e6edf3", font=("TkDefaultFont", 7))
                n = need.get(s, 0)
                c.create_text(x0 + px - 6, y0 + 8, text=("x%d" % n) if n else "", anchor="e",
                              fill="#ffd54a", font=("TkDefaultFont", 8, "bold"))
            else:
                c.create_text(x0 + px / 2, y0 + px / 2, text="free", fill="#4a525b", font=("TkDefaultFont", 8))
            if s == self.brush:
                c.create_rectangle(x0 + 2, y0 + 2, x0 + px - 2, y0 + px - 2, outline="#f0a030", width=3)
            if s == self.sel_slot:
                c.create_rectangle(x0 + 5, y0 + 5, x0 + px - 5, y0 + px - 5, outline="#6fb1ff", width=2)
        self.sync_options()
        cur = d.inv.get(self.sel_slot)
        self.slot_title.configure(text="Slot %d%s" % (self.sel_slot, ("  -  " + item_label(cur)) if cur else ""))
        self.item_var.set(cur or "")
        self.fav_btn.configure(text="Remove favorite" if cur and cur in self.favorites() else "Add to favorites",
                               state="normal" if cur else "disabled")
        self.refresh_favorites()
        if self.brush is None:
            self.brush_var.set("Brush: plain digging")
        else:
            self.brush_var.set("Brush: dig, then place %s (slot %d)" % (item_label(d.inv[self.brush]), self.brush))
        lines = []
        for s in sorted(d.inv):
            n = need.get(s, 0)
            extra = ""
            if n > 64:
                extra = "  (more than a stack: put %d in, I'll wait for a refill)" % 64
            lines.append("Slot %d  %s: %d to place%s" % (s, item_label(d.inv[s]), n, extra))
        if not lines:
            lines.append("No items assigned. The turtle only digs.")
        else:
            lines.append("Load these onto the turtle before it starts.")
        self.supply_var.set("\n".join(lines))

    def sync_options(self):
        self.pattern_var.set(dict(PATTERNS).get(self.design.pattern, PATTERNS[0][1]))
        self.torch_mode_var.set(dict(TORCH_MODES).get(self.design.torch_mode, TORCH_MODES[0][1]))

    def pick_pattern(self):
        if self.mode != "edit":
            self.sync_options()
            return
        key = next((k for k, label in PATTERNS if label == self.pattern_var.get()), None)
        if key and key != self.design.pattern:
            self.snapshot()
            self.design.pattern = key
            self.after_edit()

    def pick_torch_mode(self):
        if self.mode != "edit":
            self.sync_options()
            return
        key = next((k for k, label in TORCH_MODES if label == self.torch_mode_var.get()), None)
        if key and key != self.design.torch_mode:
            self.snapshot()
            self.design.torch_mode = key
            self.after_edit()

    # ------------------------------------------------------------------ interaction
    def inv_slot_at(self, e):
        px = self.SLOT_PX
        col, row = int(e.x // px), int(e.y // px)
        if 0 <= col < 4 and 0 <= row < 4:
            return row * 4 + col + 1
        return None

    def inv_click(self, e):
        s = self.inv_slot_at(e)
        if s is not None:
            self.sel_slot = s
            self.refresh_inventory()

    def inv_double(self, e):
        s = self.inv_slot_at(e)
        if s is not None:
            self.sel_slot = s
            self.use_brush()

    def set_slot_from_box(self):
        if self.mode != "edit":
            return
        name = clean_item(self.item_var.get())
        if name is None:
            self.error("Item", "That doesn't look like an item id.\nUse something like  minecraft:cobblestone  or  torch.")
            return
        self.assign_item(name)

    def assign_item(self, name, slot=None):
        """Put `name` into a turtle slot (the selected one by default). True when it worked."""
        if self.mode != "edit":
            return False
        d = self.design
        s = slot or self.sel_slot
        if d.inv.get(s) == name:
            return True
        if s not in d.inv and len(d.inv) >= MAX_SUPPLY_SLOTS:
            self.error("Item", "At most %d slots can be reserved - the turtle needs the others for "
                               "what it digs up." % MAX_SUPPLY_SLOTS)
            return False
        self.snapshot()
        d.set_slot_item(s, name)
        self.after_edit()
        return True

    # ------------------------------------------------------------------ favorites
    def favorites(self):
        favs = self.cfg.get("favorites")
        if not isinstance(favs, list):
            favs = list(DEFAULT_FAVORITES)
        return [f for f in favs if isinstance(f, str)]

    def set_favorite(self, name, on):
        favs = [f for f in self.favorites() if f != name]
        if on:
            favs.append(name)
        self.cfg["favorites"] = favs
        save_config(self.cfg)
        self.refresh_favorites()
        cur = self.design.inv.get(self.sel_slot)
        self.fav_btn.configure(text="Remove favorite" if cur and cur in favs else "Add to favorites")

    def toggle_slot_favorite(self):
        cur = self.design.inv.get(self.sel_slot)
        if cur:
            self.set_favorite(cur, cur not in self.favorites())

    def refresh_favorites(self):
        bar = getattr(self, "fav_bar", None)
        if bar is None:
            return
        for w in bar.winfo_children():
            w.destroy()
        favs = self.favorites()
        bank = self.icon_bank()
        self.fav_title.configure(text="Favorites (click to put one in slot %d)" % self.sel_slot)
        if not favs:
            ttk.Label(bar, foreground="#666", text="None yet - use 'Add to favorites' or Browse items.").pack(anchor="w")
        for i, name in enumerate(favs[:16]):
            img = bank.picture(name, 2) if bank else None
            b = tk.Button(bar, image=img, width=36, height=36, relief="groove", borderwidth=2,
                          command=lambda n=name: self.assign_item(n)) if img is not None else \
                tk.Button(bar, text=item_label(name)[:3], width=3, height=2, bg=item_color(name),
                          command=lambda n=name: self.assign_item(n))
            b.grid(row=i // 8, column=i % 8, padx=1, pady=1)
            b.bind("<Enter>", lambda e, n=name: self.fav_hint.set(item_label(n)))
            b.bind("<Leave>", lambda e: self.fav_hint.set(""))

    # ------------------------------------------------------------------ item picker window
    def open_picker(self, callback=None):
        """Browse items. With a callback, a chosen item is handed to it instead of going into a turtle slot."""
        self.pick_cb = callback
        win = getattr(self, "picker", None)
        if win is not None and win.winfo_exists():
            win.lift()
            self.picker_fill()
            return
        win = self.picker = tk.Toplevel(self.root)
        win.title("Choose an item")
        win.geometry("430x580")
        win.transient(self.root)
        top = ttk.Frame(win, padding=(8, 8, 8, 0))
        top.pack(fill="x")
        ttk.Label(top, text="Search").pack(side="left")
        self.pick_q = tk.StringVar()
        ent = ttk.Entry(top, textvariable=self.pick_q)
        ent.pack(side="left", fill="x", expand=True, padx=6)
        self.pick_q.trace_add("write", lambda *a: self.picker_fill())
        self.pick_favs_only = tk.BooleanVar(value=False)
        ttk.Checkbutton(top, text="Favorites only", variable=self.pick_favs_only,
                        command=self.picker_fill).pack(side="left")
        ttk.Label(win, foreground="#666", wraplength=400, justify="left", padding=(8, 2), text=(
            "Double-click an item to put it in the selected slot. Click the box in the Favorite column to star it. "
            "Items from mods: type their full id (like  mymod:cool_block)  and double-click the row that appears."
        )).pack(fill="x")
        style = ttk.Style(win)
        style.configure("Pick.Treeview", rowheight=26)
        mid = ttk.Frame(win, padding=8)
        mid.pack(fill="both", expand=True)
        self.pick_tree = tv = ttk.Treeview(mid, columns=("fav",), style="Pick.Treeview", selectmode="browse")
        tv.heading("#0", text="Item")
        tv.heading("fav", text="Favorite")
        tv.column("#0", width=280)
        tv.column("fav", width=70, anchor="center", stretch=False)
        sb = ttk.Scrollbar(mid, orient="vertical", command=tv.yview)
        tv.configure(yscrollcommand=sb.set)
        tv.pack(side="left", fill="both", expand=True)
        sb.pack(side="left", fill="y")
        tv.bind("<Double-1>", self.picker_double)
        tv.bind("<ButtonRelease-1>", self.picker_click)
        tv.bind("<Return>", lambda e: self.picker_use())
        bot = ttk.Frame(win, padding=(8, 0, 8, 8))
        bot.pack(fill="x")
        self.pick_info = tk.StringVar()
        ttk.Label(bot, textvariable=self.pick_info, foreground="#666").pack(anchor="w")
        row = ttk.Frame(bot)
        row.pack(fill="x", pady=(4, 0))
        self.pick_use_btn = ttk.Button(row, text="Put in slot", command=self.picker_use)
        self.pick_use_btn.pack(side="left")
        ttk.Button(row, text="Add / remove favorite", command=self.picker_toggle).pack(side="left", padx=4)
        ttk.Button(row, text="Close", command=win.destroy).pack(side="right")
        self.picker_fill()
        ent.focus_set()

    def picker_names(self):
        q = self.pick_q.get().strip().lower().replace(" ", "_")
        favs = self.favorites()
        bank = self.icon_bank()
        pool = [f for f in favs]
        if not self.pick_favs_only.get():
            seen = set(pool)
            for n in [n for n, _c in ITEM_PRESETS] + (bank.names() if bank else []):
                if n not in seen:
                    seen.add(n)
                    pool.append(n)
        out = [n for n in pool if q in n.lower()] if q else pool
        typed = clean_item(q) if q and ":" in q else None
        if typed and typed not in out:
            out.insert(0, typed)
        return out

    def picker_fill(self):
        tv = getattr(self, "pick_tree", None)
        if tv is None or not tv.winfo_exists():
            return
        names = self.picker_names()
        favs = set(self.favorites())
        bank = self.icon_bank()
        tv.delete(*tv.get_children())
        for n in names[:300]:
            img = bank.picture(n, 1) if bank else ""
            tv.insert("", "end", iid=n, text="  " + item_label(n) + ("" if n.startswith("minecraft:") else "   (" + n + ")"),
                      image=img or "", values=("[x]" if n in favs else "[ ]",))
        extra = len(names) - 300
        self.pick_info.set("%d items%s" % (len(names), "  (showing the first 300 - type to narrow)" if extra > 0 else ""))
        self.pick_use_btn.configure(text="Choose" if getattr(self, "pick_cb", None) else "Put in slot %d" % self.sel_slot)

    def picker_selected(self):
        sel = self.pick_tree.selection()
        return sel[0] if sel else None

    def picker_click(self, e):
        tv = self.pick_tree
        if tv.identify_region(e.x, e.y) == "cell" and tv.identify_column(e.x) == "#1":
            row = tv.identify_row(e.y)
            if row:
                self.set_favorite(row, row not in self.favorites())
                keep = tv.yview()
                self.picker_fill()
                tv.yview_moveto(keep[0])
                if tv.exists(row):
                    tv.selection_set(row)

    def picker_double(self, e):
        tv = self.pick_tree
        if tv.identify_region(e.x, e.y) == "tree" or tv.identify_column(e.x) == "#0":
            self.picker_use()

    def picker_use(self):
        n = self.picker_selected()
        cb = getattr(self, "pick_cb", None)
        if n and cb:
            self.picker.destroy()
            self.pick_cb = None
            cb(n)
        elif n and self.assign_item(n):
            self.picker.destroy()

    def picker_toggle(self):
        n = self.picker_selected()
        if n:
            self.set_favorite(n, n not in self.favorites())
            self.picker_fill()
            if self.pick_tree.exists(n):
                self.pick_tree.selection_set(n)

    def empty_slot(self):
        if self.mode != "edit" or self.sel_slot not in self.design.inv:
            return
        self.snapshot()
        self.design.set_slot_item(self.sel_slot, None)
        self.after_edit()

    def use_brush(self):
        if self.sel_slot not in self.design.inv:
            self.info("Brush", "Put an item in slot %d first." % self.sel_slot)
            return
        self.brush = self.sel_slot
        if self.tool.get() == "turtle":
            self.tool.set("pencil")
        self.refresh_inventory()
        self.refresh_layer()

    def dig_only(self):
        self.brush = None
        self.refresh_inventory()

    def add_torches(self):
        if self.mode != "edit":
            return
        d = self.design
        slot = next((s for s, n in sorted(d.inv.items()) if n == TORCH), None)
        if slot is None:
            free = [s for s in range(16, 0, -1) if s not in d.inv]
            if len(d.inv) >= MAX_SUPPLY_SLOTS or not free:
                self.error("Torches", "No slot left to hold torches.")
                return
            slot = free[0]
        try:
            gap = int(self.torch_gap.get())
        except (tk.TclError, ValueError):
            self.error("Torches", "Enter a whole number for the spacing.")
            return
        self.snapshot()
        had = slot in d.inv
        d.inv[slot] = TORCH
        added = auto_torches(d, gap, slot)
        if added == 0:
            self.undo.pop()
            if not had:
                del d.inv[slot]
            self.info("Torches", "No spot found. A torch is dropped onto the floor from the cell above, so it needs a dug cell above it (the design must be at least 2 layers tall) and a solid floor below.")
            return
        self.sel_slot = slot
        self.after_edit()

    def clear_all_blocks(self):
        if self.mode != "edit" or not self.design.place:
            return
        self.snapshot()
        clear_blocks(self.design)
        self.after_edit()

    # ------------------------------------------------------------------ textures: built-in or your own
    def texture_status(self):
        n = len(TEX["tiles"])
        if not n:
            return "Built-in simplified textures. Nothing imported yet."
        return "%d imported textures from: %s" % (n, ", ".join(TEX["sources"]) or "?")

    def set_texture_mode(self, mode):
        if mode == "imported" and not TEX["tiles"]:
            mode = "builtin"
        TEX["mode"] = mode
        self.cfg["texture_mode"] = mode
        save_config(self.cfg)
        bank = self.icon_bank()
        if bank:
            bank.cache.clear()
        self.mcache = {}
        self.refresh_inventory()
        self.relayout(force=True)
        if getattr(self, "picker", None) is not None and self.picker.winfo_exists():
            self.picker_fill()
        if hasattr(self, "tex_mode_var"):
            self.tex_mode_var.set(mode)
            self.tex_status.set(self.texture_status())

    def import_textures(self, paths=None):
        if paths is None:
            paths = filedialog.askopenfilenames(
                title="Choose a resource pack, a Minecraft version .jar, or a mod .jar",
                filetypes=[("Resource pack / jar", "*.zip *.jar"), ("All files", "*.*")])
        total = 0
        for path in paths or ():
            try:
                total += import_texture_file(self.root, path)
            except ValueError as ex:
                self.error("Textures", "%s\n\n%s" % (os.path.basename(path), ex))
        if total:
            self.set_texture_mode("imported")
        return total

    def remove_textures(self):
        clear_texpack()
        self.set_texture_mode("builtin")

    def open_textures(self):
        win = getattr(self, "tex_win", None)
        if win is not None and win.winfo_exists():
            win.lift()
            return
        win = self.tex_win = tk.Toplevel(self.root)
        win.title("Textures")
        win.transient(self.root)
        f = ttk.Frame(win, padding=12)
        f.pack(fill="both", expand=True)
        bold = ("TkDefaultFont", 10, "bold")
        ttk.Label(f, text="Item pictures", font=bold).pack(anchor="w")
        self.tex_mode_var = tk.StringVar(value=TEX["mode"])
        ttk.Radiobutton(f, text="Built-in simplified textures (colour-matched to Minecraft)", value="builtin",
                        variable=self.tex_mode_var, command=lambda: self.set_texture_mode("builtin")).pack(anchor="w", pady=(4, 0))
        ttk.Radiobutton(f, text="My imported textures", value="imported", variable=self.tex_mode_var,
                        command=lambda: self.set_texture_mode("imported")).pack(anchor="w")
        self.tex_status = tk.StringVar(value=self.texture_status())
        ttk.Label(f, textvariable=self.tex_status, wraplength=380, justify="left", foreground="#555").pack(anchor="w", pady=(6, 6))
        row = ttk.Frame(f)
        row.pack(fill="x")
        ttk.Button(row, text="Import resource pack / jar...", command=self.import_textures).pack(side="left")
        ttk.Button(row, text="Remove imported", command=self.remove_textures).pack(side="left", padx=6)
        ttk.Label(f, wraplength=380, justify="left", foreground="#666", text=(
            "Pick a resource pack (.zip), Minecraft's own version file (in your .minecraft/versions folder, "
            "e.g. 1.21.1/1.21.1.jar) or a mod's .jar. Items from mods get their pictures too. "
            "Everything stays on your computer. The 3D pages you export carry only the few textures they use.")
                  ).pack(anchor="w", pady=(10, 0))
        ttk.Button(f, text="Close", command=win.destroy).pack(anchor="e", pady=(10, 0))
