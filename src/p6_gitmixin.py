# GUI part: the GitHub tab and the 'Designs' window (this computer + the repository).
# ================================================================ GUI: GitHub + designs list
class GitMixin:
    """The GitHub tab and the 'Designs' window (this computer + the repo)."""

    # ---------------------------------------------------------------- tab
    def build_github_tab(self, f):
        bold = ("TkDefaultFont", 10, "bold")
        ttk.Label(f, text="Your GitHub repo", font=bold).pack(anchor="w")
        grid = ttk.Frame(f)
        grid.pack(fill="x")
        grid.columnconfigure(1, weight=1)
        for r, (label, var, show) in enumerate((
                ("Repo (owner/name)", self.repo_var, None), ("Branch", self.branch_var, None),
                ("Folder in repo", self.folder_var, None), ("Access token", self.token_var, "*"))):
            ttk.Label(grid, text=label).grid(row=r, column=0, sticky="w", pady=1)
            ttk.Entry(grid, textvariable=var, show=show, width=24).grid(row=r, column=1, sticky="ew", padx=(6, 0))
        ttk.Checkbutton(f, text="Remember token on this computer (stored unencrypted)",
                        variable=self.remember_var).pack(anchor="w")
        ttk.Checkbutton(f, text="Also publish a web page to share (3D replay + gallery)",
                        variable=self.share_var).pack(anchor="w")
        ttk.Label(f, foreground="#555", wraplength=300, justify="left", text=(
            "Use a PUBLIC repo so turtles can download without a login. Token: GitHub > Settings > "
            "Developer settings > Fine-grained tokens, limited to this repo, 'Contents: Read and write'. "
            "Every design is stored in its own file in the folder; the other designs stay untouched.")
                  ).pack(anchor="w", pady=(2, 6))
        row = ttk.Frame(f)
        row.pack(fill="x")
        ttk.Button(row, text="Upload to GitHub", command=self.upload).pack(side="left", fill="x", expand=True)
        ttk.Button(row, text="Test connection", command=self.test_connection).pack(side="left", fill="x", expand=True, padx=(4, 0))
        ttk.Label(f, text="Link to share", font=bold).pack(anchor="w", pady=(8, 0))
        row = ttk.Frame(f)
        row.pack(fill="x")
        ttk.Entry(row, textvariable=self.share_url_var, state="readonly", font=("TkFixedFont", 9)).pack(side="left", fill="x", expand=True)
        ttk.Button(row, text="Copy", command=lambda: self.copy_cmd(self.share_url_var)).pack(side="left", padx=(4, 0))
        ttk.Button(row, text="Open", command=self.open_share_url).pack(side="left", padx=(4, 0))
        ttk.Button(f, text="Open a design from a link...", command=self.open_from_link).pack(fill="x", pady=(3, 0))
        ttk.Label(f, text="Type this on the turtle", font=bold).pack(anchor="w", pady=(8, 0))
        self.cmd0_var, self.cmd1_var, self.cmd2_var = tk.StringVar(value="delete carve"), tk.StringVar(), tk.StringVar()
        for label, var in (("0. Resetting or updating the turtle? First:", self.cmd0_var),
                           ("1. Once - installs the menu:", self.cmd1_var), ("2. Then - runs this design:", self.cmd2_var)):
            ttk.Label(f, text=label, foreground="#555").pack(anchor="w", pady=(3, 0))
            row = ttk.Frame(f)
            row.pack(fill="x")
            ttk.Entry(row, textvariable=var, state="readonly", font=("TkFixedFont", 9)).pack(side="left", fill="x", expand=True)
            ttk.Button(row, text="Copy", command=lambda v=var: self.copy_cmd(v)).pack(side="left", padx=(4, 0))
        for v in (self.repo_var, self.branch_var, self.folder_var, self.name_var):
            v.trace_add("write", lambda *a: self.refresh_turtle_commands())
        self.refresh_turtle_commands()
        ttk.Button(f, text="Open designs on this PC / in the repo...", command=self.open_designs_window
                   ).pack(fill="x", pady=(6, 0))
        ttk.Button(f, text="Save this program as a .lua file...", command=self.save_lua_file
                   ).pack(fill="x", pady=(4, 0))
        ttk.Label(f, textvariable=self.gh_status, wraplength=300, justify="left").pack(anchor="w", pady=(6, 2))
        self.cmd_text = tk.Text(f, height=8, width=44, wrap="word", font=("TkFixedFont", 9))
        self.cmd_text.pack(fill="both", expand=True)

    def collect_github_cfg(self, need_token=True):
        try:
            repo, branch, folder = check_repo_settings(self.repo_var.get(), self.branch_var.get(),
                                                       self.folder_var.get())
        except UploadError as ex:
            self.gh_status.set(str(ex))
            return None
        token = self.token_var.get().strip() or os.environ.get("GITHUB_TOKEN", "").strip()
        if need_token and not token:
            self.gh_status.set("Enter your GitHub access token.")
            return None
        self.cfg.update(repo=repo, branch=branch, folder=folder,
                        live_enabled=bool(self.live_enabled_var.get()),
                        live_url=self.live_url_var.get().strip(), share=bool(self.share_var.get()))
        if self.remember_var.get() and token:
            self.cfg["token"] = token
        else:
            self.cfg.pop("token", None)
        save_config(self.cfg)
        return {"repo": repo, "branch": branch, "folder": folder, "token": token,
                "share": bool(self.share_var.get())}

    def live_url_for_upload(self):
        if not self.live_enabled_var.get():
            return ""
        url = normalize_live_url(self.live_url_var.get())
        if not url:
            self.gh_status.set("The live view address must look like  http://127.0.0.1:8765  "
                               "(or untick 'Include live reporting').")
            return None
        return url

    def upload(self):
        self.commit_name()
        cfg = self.collect_github_cfg()
        live_url = self.live_url_for_upload()
        if cfg is None or live_url is None:
            return
        design = self.design.copy()
        if build_run(design)[1] == 0:
            self.gh_status.set("Nothing to mine yet - select some cells connected to the turtle.")
            return
        self.gh_status.set("Uploading...")

        def work():
            info = publish_design(cfg, design, live_url)
            try:
                info["estimate"] = estimate(design)
            except Exception:
                info["estimate"] = None
            return info
        self.run_bg(work, self.upload_done,
                    lambda ex: self.gh_status.set(str(ex)))

    def upload_done(self, info):
        self.last_upload = info
        menu, prog = turtle_commands(info)
        self.refresh_turtle_commands()
        self.cmd2_var.set("carve %s" % info["slug"])
        self.root.clipboard_clear()
        self.root.clipboard_append(menu)
        self.gh_status.set("Uploaded \"%s\" (%d blocks). %d program%s in the repo now." % (
            info["name"], info["blocks"], info["count"], "" if info["count"] == 1 else "s")
            + ("" if info["changed"] else "  (no changes since last upload)")
            + "  The install command is copied - paste it into the turtle.")
        link = info.get("share_url", "")
        self.share_url_var.set(link)
        if link:
            self.root.clipboard_clear()
            self.root.clipboard_append(link)
            self.gh_status.set(self.gh_status.get().replace("The install command is copied - paste it into the turtle.",
                               "The share link is copied. %s" % info.get("share_note", "")).strip())
        est = info.get("estimate")
        if est and est["warnings"]:
            self.gh_status.set(self.gh_status.get() + "  Heads up: %d thing%s to check (below)." % (
                len(est["warnings"]), "" if len(est["warnings"]) == 1 else "s"))
        self.cmd_text.delete("1.0", "end")
        self.cmd_text.insert("1.0", ((estimate_text(est) + "\n\n") if est else "") + (
            "Resetting the turtle or updating the menu? Type this first:\ndelete carve\n\n"
            "On a turtle, once - installs the menu:\n%s\n\n"
            "Then, any time:\ncarve          (pick from the list)\ncarve %s\n\n"
            "Or fetch just this program:\n%s\nrun it with:  job_%s\n\n"
            "(If a file already exists on the turtle, type  delete <name>  first.)"
            % (menu, info["slug"], prog, info["slug"])))

    def open_share_url(self):
        url = self.share_url_var.get()
        if url:
            try:
                webbrowser.open(url)
            except Exception:
                pass
        else:
            self.gh_status.set("Upload a design with the web page option on first.")

    def open_from_link(self):
        from tkinter import simpledialog
        url = simpledialog.askstring("Open from link", "Paste the address of a shared design page:", parent=self.root)
        if not url:
            return
        self.gh_status.set("Fetching the design...")

        def done(design):
            self.exit_view()
            self.commit_name()
            design.name = unique_name(design.name, {e["slug"] for e in library_list()})
            self.set_design(design)
            self.gh_status.set("Opened \"%s\" from the link." % design.name)
        self.run_bg(lambda: design_from_link(url), done, lambda ex: self.gh_status.set(str(ex)))

    def refresh_turtle_commands(self):
        """Fill the two 'type this on the turtle' boxes from the repo settings and the design name."""
        if not hasattr(self, "cmd1_var"):
            return
        slug = slugify(self.name_var.get())
        try:
            repo, branch, folder = check_repo_settings(self.repo_var.get(), self.branch_var.get(), self.folder_var.get())
            self.cmd1_var.set("wget %s carve" % raw_url(repo, branch, repo_path(folder, "carve.lua")))
        except Exception:
            self.cmd1_var.set("(fill in the repo above first)")
        self.cmd2_var.set("carve %s" % slug)

    def copy_cmd(self, var):
        text = var.get()
        if text.startswith("("):
            return
        self.root.clipboard_clear()
        self.root.clipboard_append(text)
        self.gh_status.set("Copied: " + text)

    def copy_line(self, which):
        if not self.last_upload:
            self.gh_status.set("Upload a design first.")
            return
        line = turtle_commands(self.last_upload)[which]
        self.root.clipboard_clear()
        self.root.clipboard_append(line)
        self.gh_status.set("Copied: " + line)

    def test_connection(self):
        cfg = self.collect_github_cfg(need_token=False)
        if cfg is None:
            return
        self.gh_status.set("Checking...")

        def done(r):
            msgs = []
            if r["private"]:
                msgs.append("This repo is PRIVATE - turtles can't download from it. Make it public.")
            if cfg["token"] and not r["push"]:
                msgs.append("The token can't write to this repo.")
            self.gh_status.set(" ".join(msgs) or "Connected. The repo is public and the token can write.")

        self.run_bg(lambda: gh_check(cfg["repo"], cfg["token"]), done,
                    lambda ex: self.gh_status.set(str(ex)))

    def save_lua_file(self):
        self.commit_name()
        if build_run(self.design)[1] == 0:
            self.info("Nothing to mine", "Select some cells connected to the turtle first.")
            return
        live_url = self.live_url_for_upload()
        if live_url is None:
            return
        path = self.ask_save_path(defaultextension=".lua", initialfile="job_%s.lua" % self.design.slug(),
                                  filetypes=[("Lua program", "*.lua")])
        if path:
            with open(path, "w", encoding="utf-8", newline="\n") as f:
                f.write(generate_lua(self.design, live_url))
            self.gh_status.set("Saved " + path)

    # ---------------------------------------------------------------- designs window
    def open_designs_window(self):
        if self.dwin is not None:
            try:
                if self.dwin.winfo_exists():
                    self.dwin.lift()
                    self.refresh_local()
                    return
            except Exception:
                pass
        win = self.dwin = tk.Toplevel(self.root)
        win.title("Designs")
        frm = ttk.Frame(win, padding=10)
        frm.pack(fill="both", expand=True)
        frm.columnconfigure(0, weight=1)
        frm.columnconfigure(1, weight=1)
        ttk.Label(frm, text="On this computer", font=("TkDefaultFont", 10, "bold")).grid(row=0, column=0, sticky="w")
        ttk.Label(frm, text="In your GitHub repo", font=("TkDefaultFont", 10, "bold")).grid(row=0, column=1, sticky="w", padx=(10, 0))
        self.local_list = tk.Listbox(frm, width=38, height=14, exportselection=False)
        self.remote_list = tk.Listbox(frm, width=38, height=14, exportselection=False)
        self.local_list.grid(row=1, column=0, sticky="nsew")
        self.remote_list.grid(row=1, column=1, sticky="nsew", padx=(10, 0))
        b1 = ttk.Frame(frm)
        b1.grid(row=2, column=0, sticky="w", pady=4)
        ttk.Button(b1, text="Open", command=self.open_local).pack(side="left")
        ttk.Button(b1, text="Duplicate", command=self.duplicate_local).pack(side="left", padx=4)
        ttk.Button(b1, text="Delete", command=self.delete_local).pack(side="left")
        b2 = ttk.Frame(frm)
        b2.grid(row=2, column=1, sticky="w", pady=4, padx=(10, 0))
        ttk.Button(b2, text="Refresh", command=self.refresh_remote).pack(side="left")
        ttk.Button(b2, text="Open here", command=self.open_remote).pack(side="left", padx=4)
        ttk.Button(b2, text="Remove from repo", command=self.remove_remote).pack(side="left")
        ttk.Label(frm, textvariable=self.dstatus, wraplength=520, justify="left").grid(
            row=3, column=0, columnspan=2, sticky="w")
        self._local_entries, self._remote_entries = [], []
        self.refresh_local()
        self.dstatus.set("Press Refresh to list what is in the repo.")

    def _fmt(self, name, size, blocks):
        return "%s   %dx%dx%d, %s blocks" % (name, size[0], size[1], size[2], blocks)

    def _dwin_alive(self):
        try:
            return self.dwin is not None and bool(self.dwin.winfo_exists())
        except Exception:
            return False

    def refresh_local(self):
        if not self._dwin_alive():
            return
        self._local_entries = library_list()
        self.local_list.delete(0, "end")
        for e in self._local_entries:
            mark = "  *" if e["slug"] == self.design.slug() else ""
            self.local_list.insert("end", self._fmt(e["name"], e["size"], e["blocks"]) + mark)

    def _picked(self, listbox, entries):
        sel = listbox.curselection()
        return entries[sel[0]] if sel and sel[0] < len(entries) else None

    def open_local(self):
        e = self._picked(self.local_list, self._local_entries)
        if not e:
            return
        try:
            des = library_load(e["slug"])
        except Exception as ex:
            self.error("Open", "Could not read that design: %s" % ex)
            return
        self.exit_view()
        self.set_design(des)
        self.refresh_local()

    def duplicate_local(self):
        e = self._picked(self.local_list, self._local_entries)
        if not e:
            return
        try:
            des = library_load(e["slug"])
        except Exception as ex:
            self.error("Duplicate", str(ex))
            return
        des.name = unique_name(des.name + " copy", {x["slug"] for x in library_list()})
        library_save(des)
        self.refresh_local()

    def delete_local(self):
        e = self._picked(self.local_list, self._local_entries)
        if not e or not self.confirm("Delete design", "Delete '%s' from this computer?\n"
                                     "(Copies already uploaded to GitHub are not touched.)" % e["name"]):
            return
        library_delete(e["slug"])
        if e["slug"] == self.design.slug():
            rest = library_list()
            if rest:
                self.set_design(library_load(rest[0]["slug"]))
            else:
                self.new_design()
        self.refresh_local()

    def refresh_remote(self):
        cfg = self.collect_github_cfg(need_token=False)
        if cfg is None:
            self.dstatus.set(self.gh_status.get())
            return
        self.dstatus.set("Asking GitHub...")

        def done(index):
            self._remote_entries = index["programs"]
            if not self._dwin_alive():
                return
            self.remote_list.delete(0, "end")
            for p in self._remote_entries:
                size = p.get("size") or [0, 0, 0]
                if p.get("kind"):
                    label = dict(AUTO_KINDS).get(p["kind"], p["kind"])
                    self.remote_list.insert("end", "%s   (%s)" % (p.get("name", p["slug"]), label.lower()))
                else:
                    self.remote_list.insert("end", self._fmt(p.get("name", p["slug"]), size, p.get("blocks", "?")))
            self.dstatus.set("%d program(s) in %s/%s" % (len(self._remote_entries), cfg["repo"],
                                                         cfg["folder"] or ""))

        self.run_bg(lambda: read_index(cfg), done, lambda ex: self.dstatus.set(str(ex)))

    def open_remote(self):
        e = self._picked(self.remote_list, self._remote_entries)
        cfg = self.collect_github_cfg(need_token=False)
        if not e or cfg is None:
            return
        self.dstatus.set("Downloading...")
        if e.get("kind"):
            def done_auto(job):
                self.auto_load(job)
                self.dstatus.set("Loaded '%s' into the Automation tab." % job["name"])
                self.show_tab("Automation")
            self.run_bg(lambda: fetch_remote_auto(cfg, e["slug"]), done_auto, lambda ex: self.dstatus.set(str(ex)))
            return

        def done(des):
            taken = {x["slug"] for x in library_list()}
            if des.slug() in taken:
                des.name = unique_name(des.name + " (repo)", taken)
            library_save(des)
            self.exit_view()
            self.set_design(des)
            self.refresh_local()
            self.dstatus.set("Opened '%s' as a new design on this computer." % des.name)

        self.run_bg(lambda: fetch_remote_design(cfg, e["slug"]), done, lambda ex: self.dstatus.set(str(ex)))

    def remove_remote(self):
        e = self._picked(self.remote_list, self._remote_entries)
        cfg = self.collect_github_cfg()
        if not e or cfg is None:
            self.dstatus.set(self.gh_status.get() if cfg is None else "")
            return
        if not self.confirm("Remove from repo", "Remove '%s' from the GitHub repo?\n"
                            "Your copy on this computer stays." % e.get("name", e["slug"])):
            return
        self.dstatus.set("Removing...")
        self.run_bg(lambda: remove_design(cfg, e["slug"]),
                    lambda _r: (self.dstatus.set("Removed."), self.refresh_remote()),
                    lambda ex: self.dstatus.set(str(ex)))
