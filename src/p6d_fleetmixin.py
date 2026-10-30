# GUI part: the Fleet / Colony tab - turtle list, start the server, upload colony programs, lay out and send jobs.
# v7.9: 'Lay out' checks the typed start cell against the Foreman's position (a stale coordinate sent turtles hundreds of blocks away).
# ================================================================ GUI: Fleet tab
def lan_address():
    """This computer's address on the local network (best guess), or ''."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))
        return s.getsockname()[0]
    except OSError:
        return ""
    finally:
        s.close()


class FleetMixin:
    """The Fleet tab: every turtle that reports in, at a glance, with a Stop button."""
    FLEET_COLS = (("name", "Turtle", 150), ("job", "Job", 80), ("state", "State", 100), ("progress", "Progress", 80),
                  ("fuel", "Fuel", 60), ("pos", "Where", 120), ("seen", "Seen", 70), ("msg", "Message", 260))

    def build_fleet_tab(self, f):
        self.fleet = Fleet()
        self.fleet_job = None
        for tid, a in (self.cfg.get("anchors") or {}).items():          # start positions typed in earlier
            try:
                self.fleet.typed[int(tid)] = (int(a[0]), int(a[1]), int(a[2]), a[3] if a[3] in FACINGS else "north")
            except (TypeError, ValueError, IndexError):
                pass
        for tid, g in (self.cfg.get("gods") or {}).items():             # names given from the Roman gods list
            if isinstance(g, str) and str(tid).isdigit():
                self.fleet.gods[int(tid)] = g[:30]
        self.fleet.on_anchor = self.fleet_save_anchors
        bold = ("TkDefaultFont", 10, "bold")
        ttk.Label(f, text="Fleet", font=bold).pack(anchor="w")
        ttk.Label(f, foreground="#555", wraplength=330, justify="left", text=(
            "See every turtle at once: what it is doing, its fuel and place, and any problem. Programs uploaded "
            "with live reporting send a report every few seconds. Press Start listening, then open the page below "
            "(it works in any browser, also on a phone on the same network).")).pack(anchor="w", pady=(0, 4))
        row = ttk.Frame(f)
        row.pack(fill="x")
        self.fleet_btn = ttk.Button(row, text="Start listening", command=self.fleet_toggle)
        self.fleet_btn.pack(side="left")
        ttk.Button(row, text="Open the Fleet page", command=self.fleet_open_page).pack(side="left", padx=4)
        ttk.Button(row, text="Copy address", command=self.fleet_copy_address).pack(side="left")
        self.fleet_info = tk.StringVar(value="Not listening.")
        ttk.Label(f, textvariable=self.fleet_info, wraplength=330, justify="left", foreground="#333").pack(anchor="w", pady=2)
        cols = [c[0] for c in self.FLEET_COLS]
        self.fleet_tree = ttk.Treeview(f, columns=cols, show="headings", height=8, selectmode="browse")
        for key, title, w in self.FLEET_COLS:
            self.fleet_tree.heading(key, text=title)
            self.fleet_tree.column(key, width=w, minwidth=40, stretch=(key == "msg"))
        self.fleet_tree.pack(fill="both", expand=True, pady=4)
        row = ttk.Frame(f)
        row.pack(fill="x")
        ttk.Button(row, text="Stop selected", command=self.fleet_stop).pack(side="left")
        ttk.Button(row, text="Start program...", command=self.fleet_run_dialog).pack(side="left", padx=4)
        ttk.Button(row, text="Forget selected", command=self.fleet_forget).pack(side="left")
        row = ttk.Frame(f)
        row.pack(fill="x", pady=(4, 0))
        ttk.Button(row, text="Set start position...", command=self.fleet_anchor_dialog).pack(side="left")
        ttk.Button(row, text="Open the map", command=lambda: self.fleet_open_page("#map")).pack(side="left", padx=4)
        ttk.Button(row, text="Open storage", command=lambda: self.fleet_open_page("#storage")).pack(side="left", padx=4)
        ttk.Button(row, text="Send job to site...", command=self.fleet_send_dialog).pack(side="left")
        row = ttk.Frame(f)
        row.pack(fill="x", pady=(4, 0))
        ttk.Button(row, text="Colony starter...", command=lambda: self.set_mode("colony")).pack(side="left")
        self.fleet_status = tk.StringVar(value="")
        ttk.Label(f, textvariable=self.fleet_status, wraplength=330, justify="left").pack(anchor="w", pady=2)
        ttk.Label(f, foreground="#555", wraplength=330, justify="left", text=(
            "Where is the turtle?\n"
            "- Same PC (single-player): the address on the Preview tab (http://127.0.0.1:8765) works. In the world's "
            "serverconfig/computercraft-server.toml set the \"$private\" http rule to allow.\n"
            "- Other computers on your network: tick 'Accept turtles from other computers', put this PC's network "
            "address in the Address box (shown above), allow the Windows firewall prompt.\n"
            "- A server you run: do the same in the server's computercraft-server.toml. The turtles call from the "
            "server machine, so the Address must be reachable from there (this PC's LAN or public address with "
            "the port forwarded).\n"
            "Anyone who can reach the address can see the Fleet page and press Stop, so keep it on your own network.")
        ).pack(anchor="w", pady=(4, 0))
        self.fleet_refresh()

    def fleet_address(self):
        url = normalize_live_url(self.live_url_var.get())
        return url or "http://127.0.0.1:8765"

    def fleet_toggle(self):
        self.toggle_live()
        self.fleet_refresh()

    def fleet_page_url(self):
        url = self.fleet_address()
        if self.lan_var.get():
            ip = lan_address()
            if ip:
                port = urllib.parse.urlparse(url).port or 80
                return "http://%s:%d/" % (ip, port)
        return url + "/"

    def fleet_open_page(self, anchor=""):
        if not self.server and not self.start_live():
            return
        self.fleet_refresh()
        webbrowser.open(self.fleet_page_url() + anchor)

    def fleet_copy_address(self):
        self.root.clipboard_clear()
        self.root.clipboard_append(self.fleet_page_url().rstrip("/") if self.lan_var.get() else self.fleet_address())
        self.fleet_status.set("Copied. Use this as the Address for turtles on other computers.")

    def fleet_selected(self):
        sel = self.fleet_tree.selection()
        return int(sel[0]) if sel else None

    def fleet_stop(self):
        tid = self.fleet_selected()
        if tid is None:
            self.fleet_status.set("Pick a turtle in the list first.")
        elif self.fleet.command(tid, "stop"):
            self.fleet_status.set("Stop sent. The turtle gets it with its next report (a few seconds). "
                                  "'carve resume' on it continues later.")
        self.fleet_refresh()

    # ---------------------------------------------------------------- start positions (for the shared map)
    def fleet_save_anchors(self):
        self.cfg["anchors"] = {str(k): list(v) for k, v in self.fleet.typed.items()}
        self.cfg["gods"] = {str(k): v for k, v in self.fleet.gods.items()}
        save_config(self.cfg)

    def fleet_set_anchor(self, tid, x, y, z, face):
        try:
            self.fleet.set_anchor(tid, int(x), int(y), int(z), face)
        except (TypeError, ValueError) as ex:
            self.fleet_status.set("Start position: %s" % ex)
            return False
        self.fleet_status.set("Saved. Turtle #%d started at %s,%s,%s facing %s; it appears on the map." % (tid, x, y, z, face))
        self.fleet_refresh()
        return True

    def fleet_anchor_dialog(self):
        tid = self.fleet_selected()
        if tid is None:
            self.fleet_status.set("Pick a turtle in the list first.")
            return
        old = self.fleet.typed.get(tid, (0, 64, 0, "north"))
        win = tk.Toplevel(self.root)
        win.title("Start position of turtle #%d" % tid)
        win.transient(self.root)
        vs = [tk.StringVar(value=str(n)) for n in old[:3]]
        face = tk.StringVar(value=old[3])
        ttk.Label(win, wraplength=320, justify="left", text=(
            "Where is the block the turtle stood on when it started, in the real world? Press F3 in Minecraft, "
            "stand where the turtle starts and read the XYZ. Then say which way the turtle faced (the direction of "
            "'forward' when it started).")).grid(row=0, column=0, columnspan=4, padx=8, pady=8)
        for i, (lbl, v) in enumerate(zip("XYZ", vs)):
            ttk.Label(win, text=lbl).grid(row=1, column=i * 2, sticky="e", padx=(8, 2))
            ttk.Entry(win, textvariable=v, width=8).grid(row=1, column=i * 2 + 1, sticky="w")
        ttk.Label(win, text="Facing").grid(row=2, column=0, sticky="e", padx=(8, 2), pady=6)
        ttk.Combobox(win, textvariable=face, values=list(FACINGS), state="readonly", width=8).grid(row=2, column=1, sticky="w")

        def ok():
            if self.fleet_set_anchor(tid, vs[0].get(), vs[1].get(), vs[2].get(), face.get()):
                win.destroy()

        def clear():
            self.fleet.clear_anchor(tid)
            win.destroy()
            self.fleet_refresh()
        row = ttk.Frame(win)
        row.grid(row=3, column=0, columnspan=4, pady=8)
        ttk.Button(row, text="Save", command=ok).pack(side="left", padx=4)
        ttk.Button(row, text="Forget it", command=clear).pack(side="left", padx=4)
        ttk.Button(row, text="Cancel", command=win.destroy).pack(side="left", padx=4)

    # ---------------------------------------------------------------- start a program on an idle agent turtle
    def fleet_run(self, tid, slug):
        if self.fleet.command(tid, "run", slug):
            self.fleet_status.set("Order sent: turtle #%d will start '%s' within a few seconds." % (tid, slug))
        else:
            self.fleet_status.set("Turtle #%d is not an idle agent (run the 'Agent' program on it first), or '%s' is not a valid name." % (tid, slug))

    def fleet_run_dialog(self):
        tid = self.fleet_selected()
        if tid is None:
            self.fleet_status.set("Pick an agent turtle in the list first.")
            return
        win = tk.Toplevel(self.root)
        win.title("Start a program on turtle #%d" % tid)
        win.transient(self.root)
        slug = tk.StringVar()
        ttk.Label(win, wraplength=320, justify="left", text=(
            "Pick one of the programs in your repo (press Refresh in 'All designs...' first if the list is empty), "
            "or type its short name.")).grid(row=0, column=0, columnspan=2, padx=8, pady=8)
        box = ttk.Combobox(win, textvariable=slug, width=28)
        box.grid(row=1, column=0, columnspan=2, padx=8)
        box["values"] = [p["slug"] for p in getattr(self, "_remote_entries", []) or []]

        def ok():
            self.fleet_run(tid, slug.get().strip())
            win.destroy()
        row = ttk.Frame(win)
        row.grid(row=2, column=0, columnspan=2, pady=8)
        ttk.Button(row, text="Start", command=ok).pack(side="left", padx=4)
        ttk.Button(row, text="Cancel", command=win.destroy).pack(side="left", padx=4)

    # ---------------------------------------------------------------- send a job to the nearest idle agent
    def fleet_dispatch(self, slug, site, face, foot):
        try:
            tid = self.fleet.dispatch(slug, foot, site, face)
        except ValueError as ex:
            self.fleet_status.set(str(ex))
            return None
        self.fleet_status.set("Sent '%s' to turtle #%d, the nearest idle agent. It walks to %d, %d, %d and starts there." % ((slug, tid) + tuple(site)))
        self.fleet_refresh()
        return tid

    def build_colony_tab(self, f):
        """The colony starter, as a tab of its own: the five turtles are made and uploaded for you; you only give each one's
        start position and tick it once its inventory is filled."""
        saved = self.cfg.get("colony")
        try:
            jobs = colony_foreman(colony_label([clean_auto(j) for j in saved])) if saved else colony_starter()
        except (ValueError, TypeError):
            jobs = colony_starter()
        jobs = colony_foreman(jobs)                           # the foreman always comes first and knows the other jobs
        urls = dict(self.cfg.get("colony_urls") or {})        # job name -> {"cmd", "html"}: how to start it, and its page on GitHub
        plans = self.cfg.get("colony_pos") or {}              # job name -> {"x","y","z","face","filled"}
        ttk.Label(f, text="Foreman", font=("TkDefaultFont", 12, "bold")).pack(anchor="w")
        ttk.Label(f, wraplength=330, justify="left", foreground="#555", text=(
            "One turtle to start by hand. Give it a position, the materials below, and it sets up and runs the rest of the colony. "
            "Type where it stands (world X Y Z from F3, and the way it faces), tick 'Filled' once its inventory is ready.")
                  ).pack(anchor="w", pady=(0, 4))
        adv_body = ttk.Frame(f)                                 # shown by the "Advanced" button at the bottom
        top = ttk.Frame(f)
        top.pack(fill="x", pady=(0, 4))
        ttk.Button(top, text="Upload to GitHub", style="Accent.TButton", command=lambda: self.colony_upload()).pack(side="left")
        ttk.Button(top, text="Update all (latest code)", command=lambda: self.colony_upload(everything=True)).pack(side="left", padx=4)
        ttk.Label(top, text="  app v%s" % VERSION, foreground="#555").pack(side="left")
        web = ttk.Frame(f)
        web.pack(fill="x", pady=(0, 4))
        ttk.Button(web, text="Open Fleet page (map, turtles)", style="Accent.TButton", command=lambda: self.fleet_open_page()).pack(side="left")
        ttk.Button(web, text="3D map", command=lambda: self.fleet_open_page("#3d")).pack(side="left", padx=4)
        ttk.Button(web, text="Foreman: inventory and queue", command=lambda: self.fleet_open_page("#foreman")).pack(side="left")
        fgrid = ttk.Frame(f)                                    # the Foreman's card
        fgrid.pack(fill="x")
        conn = ttk.LabelFrame(adv_body, text="Connection (why turtles don't show up)", padding=4)
        conn.pack(fill="x", pady=(0, 4))
        conn_status = tk.StringVar()
        ttk.Label(conn, textvariable=conn_status, wraplength=320, justify="left").pack(anchor="w")
        crow = ttk.Frame(conn)
        crow.pack(fill="x", pady=2)
        ttk.Label(crow, text="Turtles call:").pack(side="left")
        ttk.Entry(crow, textvariable=self.live_url_var, width=28).pack(side="left", padx=4)

        def lan_changed():
            if self.lan_var.get():
                ip = lan_address()
                if ip and urllib.parse.urlparse(normalize_live_url(self.live_url_var.get()) or "").hostname in ("127.0.0.1", "localhost", None):
                    port = urllib.parse.urlparse(self.fleet_address()).port or 8765
                    self.live_url_var.set("http://%s:%d" % (ip, port))
                conn_status.set("Changed. Upload again so the turtles get the new address.")
            if self.server:
                self.stop_live()
                self.start_live()
        ttk.Checkbutton(conn, text="Turtles run on another computer or a server", variable=self.lan_var, command=lan_changed).pack(anchor="w")
        ping = tk.StringVar()
        prow = ttk.Frame(conn)
        prow.pack(fill="x", pady=2)
        ttk.Label(prow, text="Test on a turtle:").pack(side="left")
        ttk.Entry(prow, textvariable=ping, width=30, state="readonly").pack(side="left", padx=4)
        ttk.Button(prow, text="Copy", width=5, command=lambda: (self.root.clipboard_clear(), self.root.clipboard_append(ping.get()))).pack(side="left")
        ttk.Label(conn, foreground="#777", wraplength=320, justify="left", text=(
            "Run that on any turtle (install the carve menu first). It says if the address is blocked by Minecraft "
            "(computercraft-server.toml: set the \"$private\" http rule to allow) or if nothing answers.")).pack(anchor="w")
        dbg = tk.Text(conn, width=38, height=7, wrap="none", font=("TkFixedFont", 8))
        dbg.pack(fill="x", pady=(4, 0))
        dbg.configure(state="disabled")
        dev = ttk.LabelFrame(adv_body, text="Developer test: one coordinate sets up everything", padding=4)
        dev.pack(fill="x", pady=(0, 4))
        ttk.Label(dev, wraplength=320, justify="left", foreground="#555", text=(
            "Type ONE start cell (world X Y Z from F3). 'Lay out' fills every turtle's position in a row from there. "
            "'Send all to idle agents' hands each job to the nearest idle Agent turtle (run  carve agent  once on each; they need "
            "their own start position), and they walk to their spot and start by themselves.")).pack(anchor="w")
        orow = ttk.Frame(dev)
        orow.pack(fill="x", pady=2)
        ovars = [tk.StringVar(value=str((self.cfg.get("colony_origin") or ["", "", ""])[i])) for i in range(3)]
        for lbl, v in zip("XYZ", ovars):
            ttk.Label(orow, text=lbl).pack(side="left")
            ttk.Entry(orow, textvariable=v, width=7).pack(side="left", padx=(1, 6))
        small = tk.BooleanVar(value=bool(self.cfg.get("colony_test")))
        ttk.Checkbutton(dev, text="Small test sizes (2x2 tree farm, short warehouse, 2 furnaces)", variable=small).pack(anchor="w")
        drow = ttk.Frame(dev)
        drow.pack(fill="x", pady=2)
        basef = ttk.LabelFrame(f, text="Base design (pixel designer)", padding=4)
        basef.pack(fill="x", pady=(0, 4))
        use_base = tk.BooleanVar(value=bool(self.cfg.get("colony_base")))
        base_msg = tk.StringVar()
        ttk.Checkbutton(basef, text="Take every job's position from the stations marked in the Carve editor", variable=use_base).pack(anchor="w")
        ttk.Label(basef, wraplength=320, justify="left", foreground="#555", text=(
            "Draw the base in Carve mode, pick the 'Mark a station' tool and click where each turtle's job starts. The cell where the "
            "turtle T stands is the Foreman: give the Foreman a position below and every marked job follows it, "
            "also when you move a mark later.")).pack(anchor="w")
        ttk.Button(basef, text="Open the pixel designer", command=lambda: self.set_mode("carve")).pack(anchor="w", pady=2)
        ttk.Label(basef, textvariable=base_msg, wraplength=320, justify="left").pack(anchor="w")
        grid = ttk.Frame(adv_body)                              # the other turtles, out of the way
        grid.pack(fill="x")
        rows = []                                              # one dict of vars per job
        summary, status = tk.StringVar(), tk.StringVar()
        faces = list(FACINGS)

        def effective(j):
            return colony_test_variant(j) if small.get() else j

        def effective_all():                                   # every job as it will be uploaded, the foreman's list matching
            return colony_foreman([effective(j) for j in jobs if j["kind"] != "foreman"])

        def persist():
            self.cfg["colony_test"] = bool(small.get())
            self.cfg["colony_origin"] = [v.get() for v in ovars]
            self.cfg["colony_base"] = bool(use_base.get())
            self.cfg["colony"] = list(jobs)
            self.cfg["colony_pos"] = {r["job"]["name"]: {"x": r["x"].get(), "y": r["y"].get(), "z": r["z"].get(), "face": r["face"].get(),
                                                         "filled": r["filled"].get(), "started": r["started"].get()} for r in rows}
            self.cfg["colony_urls"] = dict(urls)
            save_config(self.cfg)

        def position(r):
            try:
                return int(r["x"].get()), int(r["y"].get()), int(r["z"].get())
            except ValueError:
                return None

        def fill_guide_now():
            try:
                fill_guide()
            except NameError:                                  # the first refresh runs before the guide exists
                pass

        busy = []

        def apply_base():
            """Fill the positions of the marked jobs from the base design in the Carve editor."""
            des = self.design
            if not use_base.get():
                base_msg.set("")
                return
            fr = next((r for r in rows if r["job"]["kind"] == "foreman"), None)
            origin = position(fr) if fr else None
            if not des.marks:
                base_msg.set("No stations are marked in the Carve editor yet.")
                return
            if not origin:
                base_msg.set("Give the Foreman a position (X Y Z and facing) below: it is the turtle T of the base design.")
                return
            face = fr["face"].get() if fr["face"].get() in FACINGS else "north"
            spots = base_positions(des, origin, face)
            lower = {n.lower(): v for n, v in spots.items()}
            done, missing = [], []
            for r in rows:
                if r is fr:
                    continue
                v = lower.get(r["job"]["name"].lower())
                if not v:
                    missing.append(r["job"]["name"])
                    continue
                for k, val in zip(("x", "y", "z"), v[:3]):
                    if r[k].get() != str(val):
                        r[k].set(str(val))
                if r["face"].get() != v[3]:
                    r["face"].set(v[3])
                done.append(r["job"]["name"])
            base_msg.set("%d job(s) follow the marks%s%s" % (len(done), ("; no mark for: " + ", ".join(missing)) if missing else "",
                         ("; marks with no job: " + ", ".join(n for n in spots if n.lower() not in {j["name"].lower() for j in jobs})) if any(
                             n.lower() not in {j["name"].lower() for j in jobs} for n in spots) else ""))

        def refresh(*_):
            if busy:
                return
            busy.append(1)
            try:
                apply_base()
            finally:
                busy.pop()
            seen = {t["name"].lower(): t for t in self.fleet.snapshot()}
            addr = normalize_live_url(self.live_url_var.get())
            dbg.configure(state="normal")
            dbg.delete("1.0", "end")
            dbg.insert("1.0", self.fleet.debug_text(12))
            dbg.configure(state="disabled")
            dbg.see("end")
            ping.set("carve ping %s" % (addr or "http://<this PC>:8765"))
            if not conn_status.get().startswith("Changed"):
                conn_status.set(("Fleet server: listening on port %d. " % self.server.port if self.server else
                                 "Fleet server: NOT listening yet (it starts when you upload, or press Start listening on the Fleet tab). ")
                                + ("%d turtle(s) have reported." % len(seen) if seen else "No turtle has reported yet."))
            ready = 0
            for r in rows:
                pos = position(r)
                if pos:
                    self.fleet.plan_position(r["job"]["name"], pos[0], pos[1], pos[2], r["face"].get() if r["face"].get() in FACINGS else "north")
                else:
                    self.fleet.plan_position(r["job"]["name"], 0, 0, 0, None)
                t = seen.get(r["job"]["name"].lower())
                r["state"].set(("running as %s" % (t["label"] or "#%d" % t["id"])) if t else "not started")
                if t and not r["autoticked"]:
                    r["autoticked"] = True
                    r["started"].set(True)                       # it reported in, so it has been started
                if pos and r["filled"].get():
                    ready += 1
            started = sum(1 for r in rows if r["started"].get())
            summary.set("%d of %d turtles have a position and are filled; %d started.%s" % (
                ready, len(rows), started, "  All ready: start them in this order, one by one." if rows and ready == len(rows) and not started else ""))
            fill_guide_now()
            persist()

        def draw():
            jobs[:] = colony_foreman(jobs)
            for w in grid.winfo_children() + fgrid.winfo_children():
                w.destroy()
            del rows[:]
            cnt = {str(grid): 0, str(fgrid): 0}
            for j in jobs:
                g = fgrid if j["kind"] == "foreman" else grid
                p = plans.get(j["name"], {})
                r = {"job": j, "x": tk.StringVar(value=str(p.get("x", ""))), "y": tk.StringVar(value=str(p.get("y", ""))),
                     "z": tk.StringVar(value=str(p.get("z", ""))), "face": tk.StringVar(value=p.get("face", "north")),
                     "filled": tk.BooleanVar(value=bool(p.get("filled"))), "state": tk.StringVar(),
                     "started": tk.BooleanVar(value=bool(p.get("started"))), "cmd": tk.StringVar(), "autoticked": bool(p.get("started"))}
                rows.append(r)
                i = cnt[str(g)]
                cnt[str(g)] += 1
                ttk.Label(g, text=("%s  -  %s" % (j.get("label", ""), j["name"])) if j["kind"] == "foreman" else "%s  -  %s (%s)" % (
                    j.get("label", ""), j["name"], dict(AUTO_KINDS)[j["kind"]].split(" (")[0]),
                          font=("TkDefaultFont", 9, "bold")).grid(row=4 * i, column=0, columnspan=3, sticky="w", pady=(8, 0))
                ttk.Label(g, textvariable=r["state"], foreground="#555").grid(row=4 * i, column=3, columnspan=2, sticky="e", pady=(8, 0))
                ttk.Label(g, text="needs: " + COLONY_NEEDS.get(j["kind"], ""), foreground="#777", wraplength=330, justify="left").grid(
                    row=4 * i + 1, column=0, columnspan=5, sticky="w")
                for c, k in enumerate(("x", "y", "z")):
                    ttk.Entry(g, textvariable=r[k], width=6).grid(row=4 * i + 2, column=c, sticky="w", padx=1)
                    r[k].trace_add("write", refresh)
                ttk.Combobox(g, textvariable=r["face"], values=faces, state="readonly", width=6).grid(row=4 * i + 2, column=3, padx=1)
                r["face"].trace_add("write", refresh)
                r["filled"].trace_add("write", refresh)
                ttk.Checkbutton(g, text="Filled", variable=r["filled"]).grid(row=4 * i + 2, column=4, padx=4)
                r["started"].trace_add("write", refresh)
                u = urls.get(j["name"])
                r["cmd"].set(u["cmd"] if u else "(not uploaded yet)  carve %s" % slugify(j["name"]))
                ttk.Entry(g, textvariable=r["cmd"], width=33, state="readonly").grid(row=4 * i + 3, column=0, columnspan=3, sticky="we", padx=1, pady=(2, 0))
                ttk.Button(g, text="Copy", width=5, command=lambda r=r: (self.root.clipboard_clear(), self.root.clipboard_append(r["cmd"].get()))).grid(
                    row=4 * i + 3, column=3, pady=(2, 0))
                ttk.Checkbutton(g, text="Started", variable=r["started"]).grid(row=4 * i + 3, column=4, padx=4, pady=(2, 0))
            refresh()
        draw()
        add = ttk.Frame(adv_body)
        add.pack(fill="x", pady=6)
        kind = tk.StringVar(value=AUTO_KINDS[0][1])
        ttk.Label(add, text="Add another:").pack(side="left")
        ttk.Combobox(add, textvariable=kind, values=[l for _k, l in AUTO_KINDS], state="readonly", width=24).pack(side="left", padx=4)

        def upload(*_, everything=False):
            self.live_enabled_var.set(True)                    # the hauler, the keeper's page and the Fleet page all need live reporting
            if not self.server:
                self.start_live()                              # ...and something to report to
            conn_status.set("")
            cfg = self.collect_github_cfg()
            live = self.live_url_for_upload()
            if cfg is None or live is None:
                status.set(self.gh_status.get() or "Fill in the GitHub tab first.")
                return
            status.set(("Updating GitHub with this version's code (%d colony programs + your other automation jobs)..." if everything
                        else "Uploading %d programs...") % len(jobs))
            todo = effective_all()

            def work():
                # the first-start programs for turtles the Foreman builds: the Agent and the carve menu
                ag = publish_auto(cfg, clean_auto(AGENT_DEFAULT), live)
                patched = [dict(j, agent_url=ag.get("program_url", ""), launcher_url=ag.get("launcher_url", "")) if j["kind"] == "foreman" else j
                           for j in todo]
                infos = [publish_auto(cfg, j, live) for j in patched]
                extra = 0
                if everything:                                 # every other automation job already in the repo gets rebuilt too
                    have = {auto_slug(j) for j in todo} | {"agent"}
                    for e in read_index(cfg)["programs"]:
                        if e.get("auto") and e.get("slug") not in have:
                            publish_auto(cfg, fetch_remote_auto(cfg, e["slug"]), live)
                            extra += 1
                return infos, extra

            def done(result):
                infos, extra = result
                for j, info in zip(todo, infos):
                    urls[j["name"]] = {"cmd": turtle_commands(info)[1],
                                       "html": info.get("html_url", "")}
                    for r in rows:
                        if r["job"]["name"] == j["name"]:
                            r["cmd"].set(urls[j["name"]]["cmd"])
                persist()
                self.refresh_turtle_commands()
                menu, _p = turtle_commands(infos[-1])
                self.root.clipboard_clear()
                self.root.clipboard_append(menu)
                if everything:
                    status.set("GitHub is up to date with Replicating Turtles v%s (%s): %d colony programs%s, and the carve menu. "
                               "Each program starts with a line naming the version. Turtles fetch it the next time you run them." % (
                                   VERSION, time.strftime("%H:%M"), len(infos), (" + %d others" % extra) if extra else ""))
                else:
                    status.set("Uploaded %d programs. On each turtle type its command (Copy), then run  job_<name>  (or install the carve menu once and run  carve <name>). "
                               "Tick Started when it is running." % len(infos))
            self.run_bg(work, done, lambda ex: status.set(str(ex)))

        def add_one():
            key = {l: k for k, l in AUTO_KINDS}.get(kind.get())
            if key == "foreman":
                status.set("There is only one foreman; it already sets up all the others.")
                return
            try:
                jobs.append(colony_extra(jobs, key))
            except ValueError as ex:
                status.set(str(ex))
                return
            draw()
            upload()
        def lay_out():
            try:
                origin = tuple(int(v.get()) for v in ovars)
            except ValueError:
                status.set("Type the start cell as three whole numbers (X Y Z).")
                return
            note = ""
            # v7.9: a start cell far from the Foreman is almost certainly a typo or an old coordinate; use a spot 12 blocks east of the Foreman instead.
            fw = self.fleet.foreman_world()
            if fw and max(abs(origin[0] - fw[0]), abs(origin[1] - fw[1]), abs(origin[2] - fw[2])) > 100:   # a typo or an old coordinate: the jobs would walk for hundreds of blocks
                origin = (fw[0] + 12, fw[1], fw[2])
                for v, n in zip(ovars, origin):
                    v.set(str(n))
                note = " (the start cell you typed was far from the Foreman, so I used a spot 12 blocks east of it)"
            spots = colony_layout(effective_all(), origin)
            for r in rows:
                x, y, z = spots[r["job"]["name"]]
                r["x"].set(str(x)); r["y"].set(str(y)); r["z"].set(str(z)); r["face"].set("north")
            status.set("Positions filled in a row from %d %d %d, all facing north.%s Check them, then 'Send all to idle agents'." % (origin + (note,)))

        def send_all():
            sent, failed = [], []
            for r in rows:
                if r["job"]["kind"] == "foreman":                      # it is started by hand, then it does this itself
                    continue
                pos = position(r)
                j = effective(r["job"])
                if not pos:
                    failed.append("%s: no position" % j["name"])
                    continue
                try:
                    tid = self.fleet.dispatch(slugify(j["name"]), auto_footprint(j), pos, r["face"].get() if r["face"].get() in FACINGS else "north")
                except ValueError as ex:
                    failed.append("%s: %s" % (j["name"], ex))
                    continue
                sent.append("%s -> #%d" % (j["name"], tid))
                r["started"].set(True)
            status.set(("Sent: " + ", ".join(sent) + ". " if sent else "") + ("Not sent: " + "; ".join(failed) if failed else "All sent."))
            self.fleet_refresh()
        ttk.Button(drow, text="Lay out", command=lay_out).pack(side="left")
        ttk.Button(drow, text="Send all to idle agents", command=send_all).pack(side="left", padx=4)
        small.trace_add("write", lambda *a: persist())
        ttk.Button(add, text="Add", command=add_one).pack(side="left")
        ttk.Button(add, text="Upload again", command=upload).pack(side="left", padx=6)
        ttk.Label(f, textvariable=summary, font=("TkDefaultFont", 10, "bold"), wraplength=330, justify="left").pack(anchor="w")
        ttk.Label(f, textvariable=status, wraplength=330, foreground="#555", justify="left").pack(anchor="w", pady=(2, 4))
        guide = tk.Text(f, width=38, height=17, wrap="word")
        guide.pack(fill="both", expand=True, pady=4)

        def fill_guide():
            eff = effective_all()
            text = colony_materials_text(eff)
            if guide.get("1.0", "end-1c") != text:
                guide.configure(state="normal")
                guide.delete("1.0", "end")
                guide.insert("1.0", text)
                guide.configure(state="disabled")
        fill_guide()

        adv_open = tk.BooleanVar(value=False)
        adv_btn = ttk.Button(f)

        def toggle_adv():
            adv_open.set(not adv_open.get())
            if adv_open.get():
                adv_body.pack(fill="x", after=adv_btn)
            else:
                adv_body.pack_forget()
            adv_btn.configure(text=("\u25be " if adv_open.get() else "\u25b8 ") + "Advanced: connection test, the other turtles, developer test")
        adv_btn.configure(command=toggle_adv)
        adv_btn.pack(anchor="w", pady=(6, 0))
        toggle_adv(); toggle_adv()                             # sets the label, stays closed
        self.colony_advanced = toggle_adv
        self.colony_frames = {"foreman": fgrid, "others": grid, "advanced": adv_body}

        def tick():                                            # keep "running as ..." up to date
            refresh()
            self.root.after(3000, tick)
        self.root.after(3000, tick)
        self.colony_rows, self.colony_summary, self.colony_upload, self.colony_ping = rows, summary, upload, ping
        self.marks_changed = refresh
        use_base.trace_add("write", lambda *a: refresh())
        self.mark_box["values"] = [r["job"]["name"] for r in rows]
        self.colony_base = {"use": use_base, "msg": base_msg}
        self.colony_dev = {"origin": ovars, "small": small, "lay_out": lay_out, "send_all": send_all, "status": status}

    def fleet_send_dialog(self):
        win = tk.Toplevel(self.root)
        win.title("Send a job to a site")
        win.transient(self.root)
        slug, face = tk.StringVar(), tk.StringVar(value="north")
        vs = [tk.StringVar(value="0"), tk.StringVar(value="64"), tk.StringVar(value="0")]
        sel = self.fleet_selected()
        for r in self.fleet.snapshot():
            if r["id"] == sel and r["world"]:
                for v, n in zip(vs, r["world"]):
                    v.set(str(n))
        entries = {}
        ttk.Label(win, wraplength=340, justify="left", text=(
            "The job goes to the nearest idle agent turtle. It walks to the start cell you give (where the job's turtle "
            "would stand, in world coordinates from F3), faces the way you choose, and runs the program. "
            "A job that would overlap one already sent is refused.")).grid(row=0, column=0, columnspan=4, padx=8, pady=8)
        ttk.Label(win, text="Program").grid(row=1, column=0, sticky="e", padx=(8, 2))
        box = ttk.Combobox(win, textvariable=slug, width=26)
        box.grid(row=1, column=1, columnspan=3, sticky="w")
        for i, (lbl, v) in enumerate(zip("XYZ", vs)):
            ttk.Label(win, text=lbl).grid(row=2, column=i, sticky="e", padx=(8, 2), pady=6)
            ttk.Entry(win, textvariable=v, width=7).grid(row=3, column=i, sticky="w", padx=(8, 2))
        ttk.Label(win, text="Facing").grid(row=2, column=3, sticky="w", padx=(8, 2))
        ttk.Combobox(win, textvariable=face, values=list(FACINGS), state="readonly", width=8).grid(row=3, column=3, sticky="w")
        status = tk.StringVar()
        ttk.Label(win, textvariable=status, wraplength=340, foreground="#555").grid(row=5, column=0, columnspan=4, padx=8)

        def fill(entry_list):
            for e in entry_list:
                entries[e["slug"]] = e
            box["values"] = sorted(entries)
        fill(getattr(self, "_remote_entries", []) or [])

        def load():
            cfg = self.collect_github_cfg(need_token=False)
            if cfg is None:
                status.set(self.gh_status.get())
                return
            status.set("Loading the program list...")
            self.run_bg(lambda: read_index(cfg), lambda idx: (fill(idx["programs"]), status.set("%d programs." % len(idx["programs"]))),
                        lambda ex: status.set(str(ex)))

        def send():
            e = entries.get(slug.get().strip())
            try:
                site = [int(v.get()) for v in vs]
            except ValueError:
                status.set("The coordinates must be whole numbers.")
                return
            foot = e.get("foot") if e else None
            if self.fleet_dispatch(slug.get().strip(), site, face.get(), foot):
                win.destroy()
            else:
                status.set(self.fleet_status.get())
        row = ttk.Frame(win)
        row.grid(row=4, column=0, columnspan=4, pady=8)
        ttk.Button(row, text="Load program list", command=load).pack(side="left", padx=4)
        ttk.Button(row, text="Send", command=send).pack(side="left", padx=4)
        ttk.Button(row, text="Cancel", command=win.destroy).pack(side="left", padx=4)

    def fleet_forget(self):
        tid = self.fleet_selected()
        if tid is not None:
            self.fleet.forget(tid)
        self.fleet_refresh()

    def fleet_refresh(self):
        """Redraw the list; repeats once a second while the window exists."""
        try:
            if not self.fleet_tree.winfo_exists():
                return
        except tk.TclError:
            return
        if self.fleet_job is not None:
            try:
                self.root.after_cancel(self.fleet_job)
            except Exception:
                pass
        keep = self.fleet_selected()
        rows = self.fleet.snapshot()
        have = {int(i) for i in self.fleet_tree.get_children()}
        for gone in have - {r["id"] for r in rows}:
            self.fleet_tree.delete(str(gone))
        for r in rows:
            prog = "%d/%d" % (r["n"], r["total"]) if r["total"] else (str(r["n"]) if r["n"] else "")
            seen = "now" if r["age"] < 5 else "%ds" % r["age"] if r["age"] < 120 else "%dm" % (r["age"] // 60)
            where = "%d,%d,%d" % tuple(r["world"]) if r["world"] else "start %+d,%+d,%+d" % (r["x"], r["y"], r["z"])
            vals = (r["label"] or r["name"] or "#%d" % r["id"], r["kind"], r["state"], prog, r["fuel"], where, seen, r["msg"])
            if str(r["id"]) in self.fleet_tree.get_children():
                self.fleet_tree.item(str(r["id"]), values=vals)
            else:
                self.fleet_tree.insert("", "end", iid=str(r["id"]), values=vals)
        if keep is not None and self.fleet_tree.exists(str(keep)):
            self.fleet_tree.selection_set(str(keep))
        if self.server:
            self.fleet_btn.configure(text="Stop listening")
            self.fleet_info.set("Listening on port %d. Page: %s  -  %d turtle(s) known." % (
                self.server.port, self.fleet_page_url(), len(rows)))
        else:
            self.fleet_btn.configure(text="Start listening")
            self.fleet_info.set("Not listening.")
        self.fleet_job = self.root.after(1000, self.fleet_refresh)
