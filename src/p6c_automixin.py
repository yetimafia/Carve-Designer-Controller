# GUI part: the Automation tab (tree farm, smelter, crafter ... settings and the text pictures of their layouts).
# ================================================================ GUI: Automation tab
def auto_diagram(p):
    """A small text picture of how a job is laid out."""
    p = clean_auto(p)
    if p["kind"] == "treefarm":
        cols, rows, S = min(p["cols"], 6), min(p["rows"], 4), min(p["spacing"], 5)
        out = []
        for j in range(rows):
            lane = "+" + "".join((("-" * (S - 1)) + "o") for _ in range(cols))      # o = where it stands
            tree = " " + "".join((" " * (S - 1)) + "T" for _ in range(cols))
            out.append(lane + ("  ..." if p["cols"] > cols else ""))
            out.append(tree)
            if j < rows - 1:
                out.append("|")
        if p["rows"] > rows:
            out.append("... (%d rows)" % p["rows"])
        out.append("")
        out.append("+ = the START column (walkway, keep it free), o = where it stands, T = a tree")
        out.append("[chest] directly behind the START (below the first +)" if p["chest"] else "no chest")
        return "\n".join(out)
    if p["kind"] == "smelter":
        n = min(p["furnaces"], 10)
        return "\n".join([
            "  " + " ".join("F" for _ in range(n)) + ("  ..." if p["furnaces"] > n else "") + "     F = furnace (%d), free air above and below" % p["furnaces"],
            "  " + " ".join("-" for _ in range(n)) + "     the turtle's walkway",
            "[out] S             S = START, [out] = result chest on its left",
            "      [in]          [in] = chest behind it: raw items + %s" % item_label(p["fuel"]).lower(),
        ])
    if p["kind"] == "hauler":
        rows = []
        for l in p["legs"]:
            rows.append("[%s out] --%s--> [%s in]" % (l["from"], l["item"] or "everything", l["to"]))
        return "\n".join(rows + ["", "It stands on top of each chest, takes from the first and drops into the second."])
    if p["kind"] == "keeper":
        return "\n".join([
            "      [above]", "[left] <- corridor -> [right]   x %d steps, 4 storage chests per step" % p["length"], "      [below]", "",
            "[pickup]  S  ---> corridor ...      [pickup] = chest left of the start: what you ask for",
            "        [drop]                      [drop]   = chest behind it: put things in here"])
    if p["kind"] == "miner":
        return "\n".join([
            "  S  <- start (chest behind it)", "  |", "  |  shaft %d down" % p["depth"], "  |",
            "  +----+----+----+----> main tunnel %d long" % p["reach"],
            "       |    |    |", "       |    |    |   side tunnels (%d long) every 3 blocks, both sides" % p["rib"],
            "", "It scans every wall and mines any wanted ore it sees."])
    if p["kind"] == "scout":
        return "\n".join([
            "      ^ up %d" % p["up"], "      |", "  <---+--->   +/- %d blocks each way (S = start)" % p["radius"], "      |",
            "      v down %d" % p["down"], "",
            "It walks and flies through open space, looking at every side,",
            "and the blocks it sees appear on the Fleet map."])
    if p["kind"] == "agent":
        return "\n".join(["  [ idle ]  --- order from the Fleet tab or another turtle --->  [ runs carve <program> ]",
                           "", "When the program ends it goes back to waiting."])
    cells = [(item_label(g) if g else "-")[:11] for g in p["grid"]]
    rows = ["| " + " | ".join(c.ljust(11) for c in cells[i:i + 3]) + " |" for i in (0, 3, 6)]
    return "\n".join(rows + ["", "[in] chest behind the START: ingredients      [out] chest on its left: results"])


class AutoMixin:
    """The Automation tab: ready-made tree farm, auto smelter and auto crafter programs."""

    def build_auto_tab(self, f):
        bold = ("TkDefaultFont", 10, "bold")
        self.auto_kind = tk.StringVar(value="Tree farm")
        self.auto_name = tk.StringVar(value="Tree farm")
        self.auto_vars = {
            "cols": tk.StringVar(value="3"), "rows": tk.StringVar(value="3"), "spacing": tk.StringVar(value="4"),
            "sapling": tk.StringVar(value="Oak"), "bonemeal": tk.BooleanVar(value=False), "wait": tk.StringVar(value="600"),
            "cycles": tk.StringVar(value="0"), "chest": tk.BooleanVar(value=True),
            "furnaces": tk.StringVar(value="4"), "once": tk.BooleanVar(value=False),
            "total": tk.StringVar(value="0"),
            "hwait": tk.StringVar(value="20"),
            "klen": tk.StringVar(value="8"), "kwait": tk.StringVar(value="10"), "krescan": tk.StringVar(value="1800"),
            "depth": tk.StringVar(value="20"), "reach": tk.StringVar(value="30"), "rib": tk.StringVar(value="12"),
            "radius": tk.StringVar(value="24"), "up": tk.StringVar(value="8"), "down": tk.StringVar(value="4"),
        }
        self.auto_legs = [{k: tk.StringVar() for k in ("from", "to", "item")} for _ in range(4)]
        self.auto_want = {k: tk.BooleanVar(value=True) for k, _l in MINER_RESOURCES}
        self.auto_fuel = "minecraft:coal"
        self.auto_grid = [None] * 9
        self.auto_out = ""
        ttk.Label(f, text="Automation", font=bold).pack(anchor="w")
        ttk.Label(f, foreground="#555", wraplength=330, justify="left", text=(
            "Ready-made turtle programs that keep working: a tree farm, an auto smelter and an auto crafter. "
            "Set them up here, upload them like a design, then run  carve <name>  on the turtle.")).pack(anchor="w", pady=(0, 4))
        row = ttk.Frame(f)
        row.pack(fill="x")
        ttk.Label(row, text="Type").pack(side="left")
        box = ttk.Combobox(row, textvariable=self.auto_kind, state="readonly", width=16, values=[l for _k, l in AUTO_KINDS])
        box.pack(side="left", padx=4)
        box.bind("<<ComboboxSelected>>", lambda e: self.auto_switch())
        ttk.Label(row, text="Name").pack(side="left", padx=(8, 0))
        ttk.Entry(row, textvariable=self.auto_name, width=16).pack(side="left", padx=4)
        self.auto_body = ttk.Frame(f)
        self.auto_body.pack(fill="x", pady=6)
        self.auto_text = tk.Text(f, height=15, width=48, wrap="word", font=("TkFixedFont", 9))
        self.auto_text.pack(fill="both", expand=True)
        row = ttk.Frame(f)
        row.pack(fill="x", pady=(6, 0))
        ttk.Button(row, text="Upload to GitHub", command=self.auto_upload).pack(side="left", fill="x", expand=True)
        ttk.Button(row, text="Save .lua file...", command=self.auto_save_lua).pack(side="left", fill="x", expand=True, padx=(4, 0))
        self.auto_status = tk.StringVar(value="")
        ttk.Label(f, textvariable=self.auto_status, wraplength=330, justify="left").pack(anchor="w", pady=(4, 0))
        self.auto_switch()

    def show_tab(self, title):
        try:
            self.nb.select(self.tabs[title])
        except (KeyError, tk.TclError):
            pass

    def auto_kind_key(self):
        return {l: k for k, l in AUTO_KINDS}.get(self.auto_kind.get(), "treefarm")

    def auto_switch(self):
        kind = self.auto_kind_key()
        default = auto_default(kind)
        if self.auto_name.get() in {auto_default(k)["name"] for k, _l in AUTO_KINDS} or not self.auto_name.get().strip():
            self.auto_name.set(default["name"])
        for w in self.auto_body.winfo_children():
            w.destroy()
        b, v = self.auto_body, self.auto_vars

        def spin(parent, label, var, lo, hi, width=5):
            r = ttk.Frame(parent)
            r.pack(fill="x", pady=1)
            ttk.Label(r, text=label, width=24).pack(side="left")
            ttk.Spinbox(r, from_=lo, to=hi, width=width, textvariable=var, command=self.auto_refresh).pack(side="left")
            var.trace_add("write", lambda *a: self.auto_refresh())

        def check(parent, label, var):
            ttk.Checkbutton(parent, text=label, variable=var, command=self.auto_refresh).pack(anchor="w")
        if kind == "treefarm":
            spin(b, "Trees per row", v["cols"], 1, 12)
            spin(b, "Rows", v["rows"], 1, 12)
            spin(b, "Space between trees", v["spacing"], 3, 8)
            r = ttk.Frame(b)
            r.pack(fill="x", pady=1)
            ttk.Label(r, text="Sapling", width=24).pack(side="left")
            sb = ttk.Combobox(r, textvariable=v["sapling"], state="readonly", width=18, values=[l for _k, l in SAPLINGS])
            sb.pack(side="left")
            sb.bind("<<ComboboxSelected>>", lambda e: self.auto_refresh())
            check(b, "Use bone meal (slot 2) - trees grow at once", v["bonemeal"])
            spin(b, "Wait between rounds (s)", v["wait"], 30, 7200)
            spin(b, "Rounds (0 = forever)", v["cycles"], 0, 999)
            check(b, "Chest directly behind the start", v["chest"])
        elif kind == "smelter":
            spin(b, "Furnaces", v["furnaces"], 1, 16)
            r = ttk.Frame(b)
            r.pack(fill="x", pady=1)
            ttk.Label(r, text="Fuel", width=24).pack(side="left")
            self.auto_fuel_btn = ttk.Button(r, text=item_label(self.auto_fuel), command=self.auto_pick_fuel)
            self.auto_fuel_btn.pack(side="left")
            check(b, "Stop when the input chest is empty", v["once"])
        elif kind == "hauler":
            ttk.Label(b, foreground="#555", wraplength=330, justify="left", text=(
                "Each leg: take from the OUTPUT chest of one job, put in the INPUT chest of another. Use the job's name. "
                "Item filter = part of an item name (log, charcoal); empty = everything.")).pack(anchor="w")
            names = lambda: self.fleet.stations() if hasattr(self, "fleet") else []
            for i, leg in enumerate(self.auto_legs):
                r = ttk.Frame(b)
                r.pack(fill="x", pady=1)
                ttk.Label(r, text="%d" % (i + 1), width=2).pack(side="left")
                for key, w in (("from", 14), ("to", 14)):
                    ttk.Combobox(r, textvariable=leg[key], width=w, postcommand=lambda: None).pack(side="left", padx=1)
                    leg[key].trace_add("write", lambda *a: self.auto_refresh())
                    if key == "from":
                        ttk.Label(r, text="->").pack(side="left")
                ttk.Entry(r, textvariable=leg["item"], width=9).pack(side="left", padx=(3, 0))
                leg["item"].trace_add("write", lambda *a: self.auto_refresh())
            for w in b.winfo_children():
                for c in w.winfo_children():
                    if isinstance(c, ttk.Combobox):
                        c.configure(postcommand=lambda c=c: c.configure(values=names()))
            ttk.Label(b, foreground="#666", text="Columns: take from  ->  put in   |  item filter").pack(anchor="w")
            spin(b, "Wait when idle (s)", v["hwait"], 5, 600)
            spin(b, "Rounds (0 = forever)", v["cycles"], 0, 9999)
        elif kind == "keeper":
            ttk.Label(b, foreground="#555", wraplength=330, justify="left", text=(
                "Give it a chest in the first slot (and more chests plus fuel in other slots) and start it: it places a DROP chest behind it, "
                "a PICKUP chest on its left, and builds storage chests along a corridor as it needs room. See and order items on the Fleet page, Storage tab.")).pack(anchor="w")
            spin(b, "Corridor length (steps)", v["klen"], 1, 30)
            spin(b, "Wait between checks (s)", v["kwait"], 3, 300)
            spin(b, "Re-count chests every (s)", v["krescan"], 0, 86400)
        elif kind == "miner":
            spin(b, "Shaft depth (blocks)", v["depth"], 4, 120)
            spin(b, "Main tunnel length", v["reach"], 3, 96)
            spin(b, "Side tunnel length", v["rib"], 0, 32)
            ttk.Label(b, text="Look for").pack(anchor="w")
            row = ttk.Frame(b)
            row.pack(anchor="w")
            for i, (k, label) in enumerate(MINER_RESOURCES):
                ttk.Checkbutton(row, text=label, variable=self.auto_want[k], command=self.auto_refresh).grid(row=i // 4, column=i % 4, sticky="w")
        elif kind == "scout":
            spin(b, "Radius (blocks)", v["radius"], 4, 64)
            spin(b, "Up from the start", v["up"], 0, 40)
            spin(b, "Down from the start", v["down"], 0, 40)
        elif kind == "agent":
            ttk.Label(b, foreground="#555", wraplength=330, justify="left",
                      text="Nothing to set. Name it, upload it, and it waits for orders.").pack(anchor="w")
        else:
            g = ttk.Frame(b)
            g.pack(anchor="w")
            self.auto_cells = []
            for i in range(9):
                btn = ttk.Button(g, text="-", width=13, command=lambda i=i: self.auto_pick_cell(i))
                btn.grid(row=i // 3, column=i % 3, padx=1, pady=1)
                btn.bind("<Button-3>", lambda e, i=i: self.auto_set_cell(i, None))
                self.auto_cells.append(btn)
            ttk.Label(b, foreground="#666", text="Click a cell to pick its item, right-click to empty it.").pack(anchor="w")
            ttk.Button(b, text="Preset: charcoal blocks (9 charcoal)", command=self.auto_preset_charcoal).pack(anchor="w", pady=2)
            spin(b, "Crafts (0 = until out)", v["total"], 0, 99999)
            check(b, "Stop when the input chest is empty", v["once"])
            self.auto_cells_refresh()
        self.auto_refresh()

    def auto_cells_refresh(self):
        for i, btn in enumerate(getattr(self, "auto_cells", [])):
            try:
                btn.configure(text=item_label(self.auto_grid[i])[:13] if self.auto_grid[i] else "-")
            except tk.TclError:
                pass

    def auto_preset_charcoal(self):
        """Nine charcoal in the grid: the crafter condenses it into charcoal blocks (a modded item; vanilla has none)."""
        self.auto_grid = ["minecraft:charcoal"] * 9
        if self.auto_name.get() in ("Auto crafter", ""):
            self.auto_name.set("Charcoal compressor")
        self.auto_cells_refresh()
        self.auto_refresh()

    def auto_set_cell(self, i, item):
        self.auto_grid[i] = item
        self.auto_cells_refresh()
        self.auto_refresh()

    def auto_pick_cell(self, i):
        self.open_picker(lambda name: self.auto_set_cell(i, name))

    def auto_pick_fuel(self):
        def got(name):
            self.auto_fuel = name
            try:
                self.auto_fuel_btn.configure(text=item_label(name))
            except tk.TclError:
                pass
            self.auto_refresh()
        self.open_picker(got)

    def auto_job(self):
        """The settings on screen as a job dict (not yet validated)."""
        kind, v = self.auto_kind_key(), self.auto_vars
        job = {"kind": kind, "name": self.auto_name.get()}
        saps = {l: k for k, l in SAPLINGS}
        if kind == "treefarm":
            job.update(cols=v["cols"].get(), rows=v["rows"].get(), spacing=v["spacing"].get(),
                       sapling=saps.get(v["sapling"].get(), "minecraft:oak_sapling"), bonemeal=v["bonemeal"].get(),
                       wait=v["wait"].get(), cycles=v["cycles"].get(), chest=v["chest"].get())
        elif kind == "smelter":
            job.update(furnaces=v["furnaces"].get(), fuel=self.auto_fuel, once=v["once"].get())
        elif kind == "hauler":
            job.update(legs=[{k: v.get() for k, v in leg.items()} for leg in self.auto_legs], wait=v["hwait"].get(), cycles=v["cycles"].get())
        elif kind == "keeper":
            job.update(length=v["klen"].get(), wait=v["kwait"].get(), rescan=v["krescan"].get())
        elif kind == "miner":
            job.update(depth=v["depth"].get(), reach=v["reach"].get(), rib=v["rib"].get(),
                       want=[k for k, _l in MINER_RESOURCES if self.auto_want[k].get()])
        elif kind == "scout":
            job.update(radius=v["radius"].get(), up=v["up"].get(), down=v["down"].get())
        elif kind == "agent":
            pass
        else:
            job.update(grid=list(self.auto_grid), total=v["total"].get(), once=v["once"].get())
        return job

    def auto_load(self, job):
        """Show a saved job on screen."""
        job = clean_auto(job)
        self.auto_kind.set(dict(AUTO_KINDS)[job["kind"]])
        self.auto_name.set(job["name"])
        self.auto_switch()
        v = self.auto_vars
        if job["kind"] == "treefarm":
            for k in ("cols", "rows", "spacing", "wait", "cycles"):
                v[k].set(str(job[k]))
            v["sapling"].set(dict(SAPLINGS).get(job["sapling"], job["sapling"]))
            v["bonemeal"].set(job["bonemeal"])
            v["chest"].set(job["chest"])
        elif job["kind"] == "hauler":
            for leg, src in zip(self.auto_legs, job["legs"] + [{}] * 4):
                for k, var in leg.items():
                    var.set(src.get(k, ""))
            v["hwait"].set(str(job["wait"]))
            v["cycles"].set(str(job["cycles"]))
        elif job["kind"] == "keeper":
            v["klen"].set(str(job["length"]))
            v["kwait"].set(str(job["wait"]))
            v["krescan"].set(str(job["rescan"]))
        elif job["kind"] == "miner":
            for k in ("depth", "reach", "rib"):
                v[k].set(str(job[k]))
            for k, var in self.auto_want.items():
                var.set(k in job["want"])
        elif job["kind"] == "scout":
            for k in ("radius", "up", "down"):
                v[k].set(str(job[k]))
        elif job["kind"] == "agent":
            pass
        elif job["kind"] == "smelter":
            v["furnaces"].set(str(job["furnaces"]))
            self.auto_fuel = job["fuel"]
            self.auto_fuel_btn.configure(text=item_label(job["fuel"]))
            v["once"].set(job["once"])
        else:
            self.auto_grid = list(job["grid"])
            v["total"].set(str(job["total"]))
            v["once"].set(job["once"])
            self.auto_cells_refresh()
        self.auto_refresh()

    def auto_refresh(self):
        if not hasattr(self, "auto_text"):
            return
        try:
            job = clean_auto(self.auto_job())
            text = auto_diagram(job) + "\n\n" + "\n".join(auto_summary(job)["lines"])
            warns = auto_summary(job)["warnings"]
            if warns:
                text += "\n\nHeads up:\n" + "\n".join("- " + w for w in warns)
            self.auto_ok = True
        except (ValueError, tk.TclError) as ex:
            text = "Check the settings: %s" % ex
            self.auto_ok = False
        self.auto_text.configure(state="normal")
        self.auto_text.delete("1.0", "end")
        self.auto_text.insert("1.0", text)
        self.auto_text.configure(state="disabled")

    def auto_valid_job(self):
        try:
            return clean_auto(self.auto_job())
        except (ValueError, tk.TclError) as ex:
            self.auto_status.set("Check the settings: %s" % ex)
            return None

    def auto_save_lua(self):
        job = self.auto_valid_job()
        if not job:
            return
        path = self.ask_save_path(defaultextension=".lua", initialfile=auto_slug(job) + ".lua", filetypes=[("Lua program", "*.lua")])
        if not path:
            return
        with open(path, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(generate_auto_lua(job))
        self.auto_status.set("Saved %s. Copy it to the turtle and run it." % path)

    def auto_upload(self):
        job = self.auto_valid_job()
        if not job:
            return
        cfg = self.collect_github_cfg()
        if cfg is None:
            self.auto_status.set(self.gh_status.get() or "Fill in the GitHub tab first.")
            return
        self.auto_status.set("Uploading...")

        def done(info):
            self.last_upload = info
            menu, prog = turtle_commands(info)
            self.refresh_turtle_commands()
            self.cmd2_var.set("carve %s" % info["slug"])
            self.root.clipboard_clear()
            self.root.clipboard_append(menu)
            extra = {"smelter": "  First run  carve %s setup  with the furnaces in the turtle." % info["slug"],
                     "miner": "  Chest behind the start, coal in the turtle.",
                     "keeper": "  A chest in the first slot, more chests and fuel in other slots. Items: Fleet page, Storage tab.",
                     "scout": "  Needs live reporting for the map, and a start position (Fleet tab).",
                     "agent": "  Start it once; then start jobs on it from the Fleet tab."}.get(info["kind"], "")
            self.auto_status.set("Uploaded \"%s\". On the turtle: carve %s.%s  The install command is copied." % (
                info["name"], info["slug"], extra))
        live_url = self.live_url_for_upload()
        if live_url is None:
            self.auto_status.set(self.gh_status.get())
            return
        self.run_bg(lambda: publish_auto(cfg, job, live_url), done, lambda ex: self.auto_status.set(str(ex)))
