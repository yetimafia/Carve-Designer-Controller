# GUI part: the preview/animation of the dig route inside the main window.
# ======================================================================== GUI: viewer
SPEEDS = (1, 2, 4, 8, 16, 32, 64, 128, 256, 512)      # events per tick (25 ticks a second)
ARROWS = {1: "▲", 2: "▶", 3: "▼", 4: "◀"}


def fmt_time(seconds):
    seconds = int(seconds)
    if seconds < 90:
        return "%ds" % seconds
    if seconds < 5400:
        return "%d min" % round(seconds / 60.0)
    return "%.1f h" % (seconds / 3600.0)


class ViewMixin:
    """Preview (simulated route) and live (real turtle) viewing of one design, layer by layer."""

    # ---------------------------------------------------------------- tab
    def build_view_tab(self, f):
        pad = {"anchor": "w"}
        bold = ("TkDefaultFont", 10, "bold")
        ttk.Label(f, text="Preview the route", font=bold).pack(**pad)
        ttk.Label(f, text="Replays exactly how the turtle would dig this shape, layer by layer "
                          "(ignores trips to empty its inventory).", wraplength=300,
                  foreground="#555").pack(**pad)
        row = ttk.Frame(f)
        row.pack(fill="x", pady=(2, 2))
        ttk.Label(row, text="Turtle skin").pack(side="left")
        self.skin_box = ttk.Combobox(row, textvariable=self.skin_var, state="readonly", width=16,
                                     values=[label for _k, label in SKINS])
        self.skin_box.pack(side="left", padx=4)
        self.skin_box.bind("<<ComboboxSelected>>", lambda e: self.pick_skin())
        ttk.Button(row, text="Colours...", command=self.pick_skin_colors).pack(side="left")
        ttk.Button(f, text="Preview path", command=self.start_preview).pack(fill="x", pady=(4, 2))
        row = ttk.Frame(f)
        row.pack(fill="x", pady=(0, 6))
        ttk.Button(row, text="Open 3D view in browser", command=self.view3d).pack(side="left", fill="x", expand=True)
        ttk.Button(row, text="Save 3D page to share...", command=lambda: self.view3d(save=True)).pack(
            side="left", fill="x", expand=True, padx=(4, 0))
        ttk.Button(f, text="Record a video for Discord...", command=lambda: self.view3d(record=True)).pack(
            fill="x", pady=(0, 6))

        row = ttk.Frame(f)
        row.pack(fill="x")
        self.btn_restart = ttk.Button(row, text="|<", width=3, command=lambda: self.seek(0))
        self.btn_restart.pack(side="left")
        self.btn_play = ttk.Button(row, text="Play", width=7, command=self.play_toggle)
        self.btn_play.pack(side="left", padx=3)
        ttk.Label(row, text="speed").pack(side="left", padx=(6, 2))
        ttk.Scale(row, from_=1, to=10, variable=self.speed_var, length=110,
                  command=lambda v: self.speed_var.set(int(round(float(v))))).pack(side="left")
        self.seek_scale = ttk.Scale(f, from_=0, to=1, variable=self.seek_var, command=self.on_scale)
        self.seek_scale.pack(fill="x", pady=(6, 0))
        ttk.Checkbutton(f, text="Follow the turtle's layer", variable=self.follow_var).pack(**pad)
        ttk.Label(f, textvariable=self.info_var, wraplength=300, justify="left").pack(pady=(4, 0), **pad)
        ttk.Button(f, text="Back to editor", command=self.exit_view).pack(fill="x", pady=(6, 10))

        ttk.Separator(f).pack(fill="x", pady=4)
        ttk.Label(f, text="Live view (the real turtle)", font=bold).pack(**pad)
        row = ttk.Frame(f)
        row.pack(fill="x", pady=(2, 0))
        ttk.Label(row, text="Address").pack(side="left")
        ttk.Entry(row, textvariable=self.live_url_var, width=26).pack(side="left", padx=4)
        ttk.Checkbutton(f, text="Include live reporting in uploaded programs",
                        variable=self.live_enabled_var).pack(**pad)
        ttk.Checkbutton(f, text="Accept turtles from other computers (LAN)",
                        variable=self.lan_var).pack(**pad)
        row = ttk.Frame(f)
        row.pack(fill="x", pady=2)
        self.btn_listen = ttk.Button(row, text="Start listening", command=self.toggle_live)
        self.btn_listen.pack(side="left")
        ttk.Button(row, text="Show live view", command=self.show_live).pack(side="left", padx=4)
        ttk.Button(row, text="Next turtle", command=self.next_turtle).pack(side="left")
        ttk.Label(f, textvariable=self.live_status, wraplength=300, justify="left").pack(pady=(2, 0), **pad)
        ttk.Label(f, foreground="#555", wraplength=300, justify="left", text=(
            "The turtle must be allowed to reach this address. In Minecraft's "
            "computercraft-server.toml, find the [[http.rules]] entry with "
            "host = \"$private\" and set its action to \"allow\" (then restart the world). "
            "It does not work on servers you don't run yourself.")).pack(pady=(2, 0), **pad)

    # ---------------------------------------------------------------- entering / leaving
    def enter_view(self, kind, design, view=None, sim=None):
        self.stop_play()
        self.mode = kind
        self.vdesign = design
        self.view = view or ViewState(design)
        self.sim = sim
        run, _t, _s = build_run(design)
        hidden = {design.chest_cell} if (design.chest and design.chest_cell) else set()
        self.unreachable = design.sel - run - hidden
        self.layer = max(1, min(design.h, self.view.pos[1]))
        try:
            self.nb.select(self.tabs["Preview / Live"])
        except Exception:
            pass
        self.relayout(force=True)

    def exit_view(self):
        self.stop_play()
        if self.mode == "edit":
            return
        self.mode = "edit"
        self.vdesign = self.view = self.sim = None
        self.recompute()
        self.relayout(force=True)

    def skin_color(self, design=None):
        d = design or self.design
        return d.skin_body if d.skin == "custom" else SKIN_COLORS.get(d.skin, "#7ddc4a")

    def pick_skin(self, key=None):
        labels = {label: k for k, label in SKINS}
        key = key or labels.get(self.skin_var.get(), "crafty")
        if self.mode == "edit":
            self.snapshot()
        self.design.skin = key
        self.skin_var.set(dict(SKINS)[key])
        self.autosave()
        self.refresh_layer()

    def pick_skin_colors(self):
        from tkinter import colorchooser
        body = colorchooser.askcolor(color=self.design.skin_body, title="Body colour", parent=self.root)
        if not body or not body[1]:
            return
        accent = colorchooser.askcolor(color=self.design.skin_accent, title="Accent colour", parent=self.root)
        self.design.skin_body = body[1].lower()
        if accent and accent[1]:
            self.design.skin_accent = accent[1].lower()
        self.pick_skin("custom")

    # ---------------------------------------------------------------- 3D page
    def view3d(self, save=False, record=False):
        """Work out the route and show it in 3D in the web browser (or save it as a page to share)."""
        self.commit_name()
        design = (self.vdesign if self.mode != "edit" and self.vdesign is not None else self.design).copy()
        if build_run(design)[1] == 0:
            self.info("Nothing to show", "Select some cells connected to the turtle first.")
            return
        path = None
        if save:
            path = self.ask_save_path(defaultextension=".html", initialfile=design.slug() + "_3d.html",
                                      filetypes=[("Web page", "*.html")])
            if not path:
                return
        self.info_var.set("Building the 3D view...")

        def work():
            sim = simulate(design)
            page = build_viewer_html(design, sim)
            target = path or os.path.join(tempfile.gettempdir(), "carve_3d_%s.html" % design.slug())
            with open(target, "w", encoding="utf-8", newline="\n") as fh:
                fh.write(page)
            return target

        def done(target):
            self.info_var.set(("Saved %s - send that one file to anyone; it opens in any browser." % target)
                              if save else ("Opened in your browser: pick a length and press Start recording, then "
                                            "keep that tab in front until it finishes." if record
                                            else "Opened the 3D view in your browser."))
            try:
                webbrowser.open("file://" + urllib.request.pathname2url(os.path.abspath(target)) + ("#record" if record else ""))
            except Exception:
                pass

        self.run_bg(work, done, lambda ex: self.error("3D view", str(ex)))

    # ---------------------------------------------------------------- preview
    def start_preview(self):
        self.commit_name()
        design = self.design.copy()
        if build_run(design)[1] == 0:
            self.info("Nothing to preview", "Select some cells connected to the turtle first.")
            return
        self.info_var.set("Working out the route...")
        self.run_bg(lambda: simulate(design),
                    lambda sim: self.preview_ready(design, sim),
                    lambda ex: self.error("Preview", str(ex)))

    def preview_ready(self, design, sim):
        self.enter_view("preview", design, sim=sim)
        self.play_idx = 0
        self._scale_busy = True
        self.seek_scale.configure(to=max(1, len(sim.events)))
        self.seek_var.set(0)
        self._scale_busy = False
        self.after_view_change()

    def seek(self, k):
        if self.mode != "preview" or not self.sim:
            return
        evs = self.sim.events
        k = max(0, min(len(evs), int(k)))
        if k < self.play_idx:
            self.view = ViewState(self.vdesign)
            self.play_idx = 0
        for ev in evs[self.play_idx:k]:
            self.view.apply(ev)
        self.play_idx = k
        self._scale_busy = True
        self.seek_var.set(k)
        self._scale_busy = False
        self.after_view_change()

    def on_scale(self, _value):
        if not self._scale_busy and self.mode == "preview":
            self.seek(float(self.seek_var.get()))

    def play_toggle(self):
        if self.mode != "preview" or not self.sim:
            return
        if self.playing:
            self.stop_play()
            return
        if self.play_idx >= len(self.sim.events):
            self.seek(0)
        self.playing = True
        self.btn_play.configure(text="Pause")
        self._play_job = self.root.after(40, self.tick_play)

    def stop_play(self):
        self.playing = False
        if self._play_job is not None:
            try:
                self.root.after_cancel(self._play_job)
            except Exception:
                pass
            self._play_job = None
        try:
            self.btn_play.configure(text="Play")
        except Exception:
            pass

    def tick_play(self):
        self._play_job = None
        if not self.playing or self.mode != "preview":
            return
        step = SPEEDS[max(1, min(10, int(self.speed_var.get()))) - 1]
        self.seek(self.play_idx + step)
        if self.play_idx >= len(self.sim.events):
            self.stop_play()
            return
        self._play_job = self.root.after(40, self.tick_play)

    def after_view_change(self):
        v = self.view
        if self.follow_var.get() and v and v.pos[1] != self.layer:
            self.layer = max(1, min(self.sd().h, v.pos[1]))
        self.refresh_layer()
        if self.mode == "preview" and self.sim:
            n = len(self.sim.events)
            done = len(v.mined) - 1
            put = ("   placed %d / %d" % (len(v.placed), self.sim.places)) if self.sim.places else ""
            self.info_var.set(
                "Step %d / %d   dug %d / %d%s\nmoves %d (fuel)   whole job about %s, %d moves"
                % (self.play_idx, n, done, self.sim.total, put, v.moves,
                   fmt_time(self.sim.seconds), self.sim.moves))

    # ---------------------------------------------------------------- live
    def toggle_live(self):
        if self.server:
            self.stop_live()
        else:
            self.start_live()

    def start_live(self):
        url = normalize_live_url(self.live_url_var.get())
        if not url:
            self.error("Live view", "Use an address like  http://127.0.0.1:8765")
            return False
        port = urllib.parse.urlparse(url).port or 80
        self.cfg["live_url"] = url
        srv = LiveServer("0.0.0.0" if self.lan_var.get() else "127.0.0.1", port, self.live_q.put, self.fleet)
        try:
            srv.start()
        except OSError as ex:
            self.error("Live view", "Could not listen on port %d: %s" % (port, ex))
            return False
        self.server = srv
        self.btn_listen.configure(text="Stop listening")
        self.live_status.set("Listening on port %d. Start a turtle program that includes live "
                             "reporting, then press 'Show live view'." % srv.port)
        self.schedule_poll()
        if hasattr(self, "fleet_btn"):
            self.fleet_refresh()
        return True

    def stop_live(self):
        if self.live_job is not None:
            try:
                self.root.after_cancel(self.live_job)
            except Exception:
                pass
            self.live_job = None
        if self.server:
            self.server.stop()
            self.server = None
        self.btn_listen.configure(text="Start listening")
        self.live_status.set("Not listening.")
        if hasattr(self, "fleet_btn"):
            self.fleet_refresh()

    def schedule_poll(self):
        if self.live_job is None and self.server:
            self.live_job = self.root.after(100, self.poll_live)

    def poll_live(self):
        self.live_job = None
        if not self.server:
            return
        changed = False
        for _ in range(300):
            try:
                p = self.live_q.get_nowait()
            except queue.Empty:
                break
            changed = self.ingest(p) or changed
        if changed or self.mode == "live":
            self.live_refresh()
        self.schedule_poll()

    def ingest(self, p):
        """Fold one turtle report in. Returns True when it concerns the turtle being shown."""
        try:
            tid = int(p.get("id", 0))
            sess = self.sessions.get(tid) or LiveSession(tid)
            sess.apply(p)
        except (ValueError, KeyError, TypeError, AttributeError):
            return False
        self.sessions[tid] = sess
        if self.live_current is None:
            self.live_current = tid
        return tid == self.live_current

    def show_live(self):
        if not self.server and not self.start_live():
            return
        self.enter_view("live", self.design)
        self.live_refresh()

    def next_turtle(self):
        ids = sorted(self.sessions)
        if len(ids) > 1:
            i = ids.index(self.live_current) if self.live_current in ids else -1
            self.live_current = ids[(i + 1) % len(ids)]
            self.live_refresh()

    def live_refresh(self):
        sess = self.sessions.get(self.live_current)
        if sess is None:
            if self.server:
                self.live_status.set("Listening... no turtle has reported yet.")
            return
        others = len(self.sessions) - 1
        if sess.design is None:
            self.live_status.set("Turtle #%d is running; waiting for its next full report (up to 30 s)."
                                 % sess.id)
            return
        pct = int(100 * sess.count / sess.total) if sess.total else 100
        state = "FINISHED" if sess.done else ("stopped" if sess.stopped else sess.msg)
        put = ("   placed %d / %d" % (sess.placed_count, sess.placed_total)) if sess.placed_total else ""
        text = "Turtle #%d \"%s\"\n%d / %d dug (%d%%)%s   fuel %s\n%s%s" % (
            sess.id, sess.name, sess.count, sess.total, pct, put, sess.fuel, state,
            ("\n(+%d other turtle%s: 'Next turtle')" % (others, "s" if others > 1 else "")) if others else "")
        self.live_status.set(text)
        if self.mode != "live":
            return
        self.info_var.set(text)
        if self.view is not sess.view:               # a different run / design: rebuild the picture
            self.enter_view("live", sess.design, view=sess.view)
        self.after_view_change()
