# Fleet: the app's picture of every turtle (status, position, inventory, orders) and the web page served at /fleet.
# Versions: inventory + crafting queue per turtle (7.x), duplicate names are numbered (7.8), jobs of a Foreman are placed by offset from the
# Foreman itself - _foreman_site (8.1), every turtle reports its inventory and 'crafty' flag (8.0).
# =================================================================== fleet (many turtles at once)
FLEET_HTML = r'''@@INCLUDE:fleet.html@@'''

_ATTENTION = re.compile(r"out of fuel|blocked|inventory full|empty me|put |can't|cannot|could not|did not|won't|"
                        r"waiting for|nothing to|stuck|too full", re.I)


def _clip(v, n=200):
    return str(v if v is not None else "")[:n]


def _num(v, default=0):
    try:
        return int(v)
    except (TypeError, ValueError):
        return default


# where each kind of job keeps its chests, as (right, up, forward) from its start cell
STATION_CHESTS = {
    "treefarm": {"out": (0, 0, -1)},
    "miner": {"out": (0, 0, -1)},
    "smelter": {"in": (0, 0, -1), "out": (-1, 0, 0)},
    "crafter": {"in": (0, 0, -1), "out": (-1, 0, 0)},
    "keeper": {"in": (0, 0, -1), "out": (-1, 0, 0)},
}

NAME_LIST = ["Abrams", "Bebop", "Dynamo", "Grey Talon", "Haze", "Infernus", "Ivy", "Kelvin", "Lady Geist", "Lash", "McGinnis", "Krill", "Paradox", "Pocket", "Seven", "Shiv", "Vindicta", "Viscous", "Warden", "Wraith", "Yamato", "Calico", "Holliday", "Vyper", "Sinclair", "Mirage", "Drifter", "Victor", "Paige", "Billy", "Rem", "Mo"]
NAME_ORDER = random.sample(NAME_LIST, len(NAME_LIST))      # one fresh shuffle per run: the first turtle is not always called the same


FACINGS = {"north": (0, -1), "east": (1, 0), "south": (0, 1), "west": (-1, 0)}


def local_to_world(anchor, rel):
    """anchor = (x, y, z, facing) is where a turtle's start cell is in the world and which way it faced;
    rel = (right, up, forward) measured from that start cell. Returns the world (x, y, z)."""
    ax, ay, az, face = anchor
    fx, fz = FACINGS[face]
    rx, rz = -fz, fx                       # "right" of the facing direction
    return (ax + rel[0] * rx + rel[2] * fx, ay + rel[1], az + rel[0] * rz + rel[2] * fz)


def world_to_local(anchor, w):
    """The opposite of local_to_world: (right, up, forward) of world point w, seen from the start cell."""
    ax, ay, az, face = anchor
    fx, fz = FACINGS[face]
    rx, rz = -fz, fx
    dx, dz = w[0] - ax, w[2] - az
    return (dx * rx + dz * rz, w[1] - ay, dx * fx + dz * fz)


def facing_code(agent_face, target_face):
    """A turtle's direction number (1 forward, 2 right, 3 back, 4 left) for facing target_face in the world,
    when its own start faced agent_face."""
    tx, tz = FACINGS[target_face]
    fx, fz = FACINGS[agent_face]
    rx, rz = -fz, fx
    lz, lx = tx * fx + tz * fz, tx * rx + tz * rz
    return {(0, 1): 1, (1, 0): 2, (0, -1): 3, (-1, 0): 4}[(lx, lz)]


def design_footprint(d):
    """Where a dig design lives, in (right, up, forward) from the start cell: [x0, y0, z0, x1, y1, z1]."""
    return [1 - d.tx, 1 - d.ty, 1 - d.tz, d.w - d.tx, d.h - d.ty, d.d - d.tz]


def auto_footprint(job):
    """The space an automation job uses (trees included), or None when it builds nothing (scout, agent)."""
    k = job["kind"]
    if k == "treefarm":
        s = job["spacing"]
        return [-3, -1, -2, s * job["cols"] + 2, 9, s * job["rows"] + 2]
    if k == "smelter":
        return [-2, -1, -2, job["furnaces"] + 1, 2, 4]
    if k == "crafter":
        return [-2, -1, -2, 2, 2, 2]
    if k == "keeper":
        return [-2, -1, -2, 2, 2, job["length"] + 1]
    if k == "miner":
        return [-1, -job["depth"] - 1, -job["rib"] - 1, job["reach"] + 1, 1, job["rib"] + 1]
    return None


def world_box(anchor, foot):
    """The world-space box (x0, y0, z0, x1, y1, z1) covered by a local footprint."""
    pts = [local_to_world(anchor, (x, y, z)) for x in (foot[0], foot[3]) for y in (foot[1], foot[4]) for z in (foot[2], foot[5])]
    return tuple(min(p[i] for p in pts) for i in range(3)) + tuple(max(p[i] for p in pts) for i in range(3))


def boxes_overlap(a, b):
    return all(a[i] <= b[i + 3] and b[i] <= a[i + 3] for i in range(3))


def _solve_facing(rel0, g0, rel1, g1):
    """Which way did the start face, judging from two GPS fixes at two places the turtle had been?"""
    dl = (rel1[0] - rel0[0], rel1[2] - rel0[2])
    dg = (g1[0] - g0[0], g1[2] - g0[2])
    if dl == (0, 0):
        return None
    for face in FACINGS:
        w = local_to_world((0, 0, 0, face), (dl[0], 0, dl[1]))
        if (w[0], w[2]) == dg:
            return face
    return None


def _block_name(v):
    v = str(v)[:48].replace("minecraft:", "")
    return v if re.fullmatch(r"[a-z0-9_:./\-]+", v) else "unknown"


class WorldMap:
    """Every block any scout has reported, in world coordinates."""
    MAX_CELLS = 600000

    def __init__(self):
        self.lock = threading.Lock()
        self.cols = {}                     # (x, z) -> {y: name index}
        self.names, self.index = [], {}
        self.count = 0

    def add(self, x, y, z, name):
        with self.lock:
            i = self.index.get(name)
            if i is None:
                i = self.index[name] = len(self.names)
                self.names.append(name)
            col = self.cols.setdefault((x, z), {})
            if y not in col:
                if self.count >= self.MAX_CELLS:
                    return False
                self.count += 1
            col[y] = i
            return True

    def view(self, cx, cz, r, mode="top", y=0):
        """Cells in a square around (cx, cz): the highest solid block of every column (top), or one layer (slice)."""
        out = []
        with self.lock:
            for x in range(cx - r, cx + r + 1):
                for z in range(cz - r, cz + r + 1):
                    col = self.cols.get((x, z))
                    if not col:
                        continue
                    if mode == "slice":
                        if y in col:
                            out.append([x, z, y, col[y]])
                    else:
                        best = None
                        for yy, i in col.items():
                            if self.names[i] != "air" and (best is None or yy > best[0]):
                                best = (yy, i)
                        if best:
                            out.append([x, z, best[0], best[1]])
            return list(self.names), out

    def view3d(self, cx, cy, cz, r, ry, limit=30000):
        """Blocks for the 3D map: every non-air block in a box around (cx, cy, cz) that touches air or unknown space (the ones
        you could see), nearest first. Returns (names, [[x, y, z, name index], ...], truncated)."""
        out = []
        with self.lock:
            def solid(x, y, z):
                col = self.cols.get((x, z))
                return col is not None and y in col and self.names[col[y]] != "air"
            for x in range(cx - r, cx + r + 1):
                for z in range(cz - r, cz + r + 1):
                    col = self.cols.get((x, z))
                    if not col:
                        continue
                    for y, i in col.items():
                        if abs(y - cy) > ry or self.names[i] == "air":
                            continue
                        if solid(x + 1, y, z) and solid(x - 1, y, z) and solid(x, y + 1, z) and solid(x, y - 1, z) and solid(x, y, z + 1) and solid(x, y, z - 1):
                            continue
                        out.append([x, y, z, i])
            names = list(self.names)
        out.sort(key=lambda c: (c[0] - cx) ** 2 + (c[1] - cy) ** 2 + (c[2] - cz) ** 2)
        return names, out[:limit], len(out) > limit

    def clear(self):
        with self.lock:
            self.cols, self.names, self.index, self.count = {}, [], {}, 0


class Fleet:
    """What every turtle has told us lately, plus the commands waiting for them (thread-safe)."""
    OFFLINE_AFTER = 45          # seconds without a report
    MAX_TURTLES = 200
    MAX_PENDING = 30000

    def __init__(self):
        self.lock = threading.Lock()
        self.turtles = {}
        self.cmds = {}
        self.typed = {}                  # id -> (x, y, z, facing): start position typed in by the user
        self.world = WorldMap()
        self.goto = {}                   # id -> (right, up, forward, direction): where an agent should walk before it starts a job
        self.auto_sites, self.layout_cursor = {}, {}
        self.fsites = {}         # foreman id -> where its jobs go (offsets from the foreman's own start cell)
        self.next_anchor = {}            # id -> (x, y, z, facing): the start position of the job an agent was sent to
        self.jobs = {}                   # id -> {"slug", "box", "t", "running"}: jobs sent with dispatch()
        self.sent = {}                   # id -> time of the last order dispatch() gave it
        self.storage = {}                # id -> what a storage keeper last reported (items, chests, ...)
        self.orders = {}                 # id -> [(item, count)] asked for on the web page, not yet handed to the keeper
        self.planned = {}                # job name (lower case) -> (x, y, z, facing): start position given before the turtle exists
        self.events = []                 # the last things that reached the server: (time, text), newest last
        self.last_contact = None         # (time, address) of the last turtle report
        self.name_order = random.sample(NAME_LIST, len(NAME_LIST))      # a fresh shuffle every run, so the first name differs
        self.gods = {}                   # id -> name given from the list of Deadlock heroes (turtles that have no label of their own)
        self.on_anchor = None            # called (no arguments) when typed anchors change, so the app can save them

    # ---------------------------------------------------------------- reports
    def _put(self, tid, **fields):
        with self.lock:
            if tid not in self.turtles and len(self.turtles) >= self.MAX_TURTLES:
                return False
            t = self.turtles.setdefault(tid, {"id": tid, "first_seen": time.time(), "history": [], "pending": []})
            save = False
            run = fields.pop("run", None)
            if run is not None and run != t.get("run"):
                t["run"] = run
                t["fix0"], t["gps_anchor"] = None, None          # a new run starts from a new place: forget the old frame
                if tid in self.next_anchor:                      # an agent that was sent to a site: its job starts there
                    self.typed[tid] = self.next_anchor.pop(tid)
                    save = True
            if tid in self.jobs and fields.get("kind") not in (None, "agent"):
                self.jobs[tid]["running"] = True
            fix, rel = fields.pop("fix", None), fields.get("rel")
            if fields.get("msg") and fields["msg"] != t.get("msg"):
                t["history"] = (t["history"] + [(time.time(), fields["msg"])])[-12:]
            t.update(fields)
            t["last_seen"] = time.time()
            t["stop_sent"] = t.get("stop_sent", False) and not fields.get("done")
            if fix and rel:
                self._take_fix(t, rel, fix)
        self._flush(tid)
        if save and self.on_anchor:
            self.on_anchor()
        return True

    @staticmethod
    def _take_fix(t, rel, fix):
        t["fix"] = fix
        if t.get("fix0") is None:
            t["fix0"] = (rel, fix)
        elif t.get("gps_anchor") is None:
            rel0, g0 = t["fix0"]
            face = _solve_facing(rel0, g0, rel, fix)
            if face:
                w = local_to_world((0, 0, 0, face), rel)
                t["gps_anchor"] = (fix[0] - w[0], fix[1] - rel[1], fix[2] - w[2], face)

    def _anchor(self, t):
        """(x, y, z, facing, where it came from) of the start cell, or None."""
        if t.get("gps_anchor"):
            return t["gps_anchor"] + ("gps",)
        typed = self.typed.get(t["id"])
        if typed:
            if t.get("fix") and t.get("rel"):                    # a GPS fix gives the exact start even without a facing
                w = local_to_world((0, 0, 0, typed[3]), t["rel"])
                fx = t["fix"]
                return (fx[0] - w[0], fx[1] - t["rel"][1], fx[2] - w[2], typed[3], "gps+typed")
            return tuple(typed) + ("typed",)
        return None

    def world_pos(self, t):
        a = self._anchor(t)
        if not a or not t.get("rel"):
            return None
        return local_to_world(a[:4], t["rel"])

    def foreman_world(self):
        """World position (x, y, z) of the Foreman, or None while it has not reported a position the app can place."""
        with self.lock:
            for t in self.turtles.values():
                if t.get("kind") == "foreman":
                    wp = self.world_pos(t)
                    if wp:
                        return tuple(int(v) for v in wp)
        return None

    def report_status(self, p):
        """A report from an automation program (POST /status)."""
        if not isinstance(p, dict) or p.get("v") != 1 or not isinstance(p.get("id"), int):
            raise ValueError("not a Carve status report")
        x, y, z = _num(p.get("x")), _num(p.get("y")), _num(p.get("z"))
        extra = {}
        if "inv" in p:
            extra["inv"] = self._inv(p.get("inv"))                  # the Foreman's inventory and crafting queue, for the Foreman tab
        if "q" in p:
            extra["q"] = self._queue(p.get("q"))
        if "crafty" in p:
            extra["crafty"] = bool(p.get("crafty"))
        res = self._put(p["id"], label=_clip(p.get("label"), 40), name=_clip(p.get("name"), 60), **extra,
                        kind=_clip(p.get("kind") or "auto", 20), x=x, y=y, z=z, rel=(x, y, z),
                        fuel=_clip(p.get("fuel"), 12), msg=_clip(p.get("msg")), act=_clip(p.get("act"), 90), lf=_num(p.get("f"), 0), n=_num(p.get("n")),
                        total=_num(p.get("total")), done=bool(p.get("done")),
                        run=_num(p.get("run"), None) if p.get("run") is not None else None, fix=self._fix(p.get("gps")))
        self._apply_planned(p["id"])
        return res

    @staticmethod
    def _inv(v):
        out = []
        if isinstance(v, list):
            for e in v[:16]:
                if (isinstance(e, list) and len(e) == 3 and isinstance(e[0], (int, float)) and isinstance(e[1], str)
                        and isinstance(e[2], (int, float))):
                    out.append([int(e[0]), _clip(e[1], 60), int(e[2])])
        return out

    @staticmethod
    def _queue(v):
        out = []
        if isinstance(v, list):
            for e in v[:40]:
                if isinstance(e, dict) and e.get("s") in ("now", "wait", "todo", "done"):
                    out.append({"t": _clip(e.get("t"), 70), "s": e["s"]})
        return out

    def plan_position(self, name, x, y, z, face):
        """Give the start position of a job by name, before its turtle has reported. It is applied as soon as (or if) a turtle of
        that name is known and has no typed position yet. face=None forgets the plan."""
        key = (name or "").strip().lower()
        if face is None:
            self.planned.pop(key, None)
        else:
            if face not in FACINGS:
                raise ValueError("facing must be north, east, south or west")
            self.planned[key] = (int(x), int(y), int(z), face)
        for tid in list(self.turtles):
            self._apply_planned(tid)
        if self.on_anchor:
            self.on_anchor()

    def _apply_planned(self, tid):
        with self.lock:
            t = self.turtles.get(tid)
            plan = self.planned.get((t.get("name") or "").strip().lower()) if t else None
            if not plan or t.get("planned_used") == plan:
                return
            t["planned_used"] = plan
            if tid in self.typed and self.typed[tid] != plan and not t.get("planned_set"):
                return                                   # the user typed a position for this turtle by hand: keep it
            self.typed[tid] = plan
            t["planned_set"] = True
        self._flush(tid)
        if self.on_anchor:
            self.on_anchor()

    @staticmethod
    def _fix(v):
        if isinstance(v, list) and len(v) == 3 and all(isinstance(n, (int, float)) for n in v):
            return tuple(int(round(n)) for n in v)
        return None

    def report_update(self, p):
        """The progress report of a dig program (POST /update): keep just the summary."""
        if not isinstance(p, dict) or p.get("v") != 1 or not isinstance(p.get("id"), int):
            return False
        done = bool(p.get("done")) or bool(p.get("stopped"))
        msg = _clip(p.get("msg"))
        if p.get("stopped") and not msg.startswith("Stopped"):
            msg = "Stopped (resumes with: carve resume)"
        rel = (_num(p.get("rx"), _num(p.get("x"))), _num(p.get("ry"), _num(p.get("y"))), _num(p.get("rz"), _num(p.get("z"))))
        return self._put(p["id"], label=_clip(p.get("label"), 40), name=_clip(p.get("name"), 60), kind="dig",
                         x=_num(p.get("x")), y=_num(p.get("y")), z=_num(p.get("z")), rel=rel, fuel=_clip(p.get("fuel"), 12),
                         msg=msg, n=_num(p.get("mined")), total=_num(p.get("total")), done=done,
                         run=_num(p.get("run"), None) if p.get("run") is not None else None, fix=self._fix(p.get("gps")))

    # ---------------------------------------------------------------- the world map
    def report_map(self, p):
        """Blocks a scout has seen (POST /map): [[right, up, forward, "name"], ...] measured from its start."""
        if not isinstance(p, dict) or p.get("v") != 1 or not isinstance(p.get("id"), int) or not isinstance(p.get("cells"), list):
            raise ValueError("not a Carve map report")
        with self.lock:
            t = self.turtles.get(p["id"])
            if t is None:
                return False
            for c in p["cells"][:2000]:
                if isinstance(c, list) and len(c) == 4 and all(isinstance(n, int) for n in c[:3]):
                    t["pending"].append((c[0], c[1], c[2], _block_name(c[3])))
            del t["pending"][:-self.MAX_PENDING]
            placed = self._anchor(t) is not None
            first = t.get("map_state") != placed
            t["map_state"] = placed
            name = t.get("label") or t.get("name") or "turtle %d" % p["id"]
        if first:
            self.note("map cells from %s: %s" % (name, "placed on the map" if placed else
                                                 "WAITING - give it a start position (Colony tab, or Fleet tab > Set start position)"))
        self._flush(p["id"])
        return True

    def map_waiting(self):
        """Scouts whose map cells can't be drawn yet because their start position isn't known."""
        with self.lock:
            return [{"id": t["id"], "name": t.get("label") or t.get("name") or "turtle %d" % t["id"], "count": len(t["pending"])}
                    for t in self.turtles.values() if t["pending"] and not self._anchor(t)]

    def _flush(self, tid):
        """Turn a turtle's waiting map cells into world cells once its place in the world is known."""
        with self.lock:
            t = self.turtles.get(tid)
            if not t or not t["pending"]:
                return
            a = self._anchor(t)
            if not a:
                return
            cells, t["pending"] = t["pending"], []
        for x, y, z, name in cells:
            w = local_to_world(a[:4], (x, y, z))
            self.world.add(w[0], w[1], w[2], name)

    def set_anchor(self, tid, x, y, z, face):
        """The user says: turtle tid started at world (x, y, z) facing face."""
        if face not in FACINGS:
            raise ValueError("facing must be north, east, south or west")
        with self.lock:
            self.typed[tid] = (int(x), int(y), int(z), face)
        self._flush(tid)
        if self.on_anchor:
            self.on_anchor()

    def clear_anchor(self, tid):
        with self.lock:
            self.typed.pop(tid, None)
        if self.on_anchor:
            self.on_anchor()

    def note(self, text, turtle=False, addr=""):
        """Write a line in the debug log (what reached the server, and what it made of it)."""
        with self.lock:
            now = time.time()
            self.events.append((now, text))
            del self.events[:-80]
            if turtle:
                self.last_contact = (now, addr)

    def debug_text(self, n=25):
        with self.lock:
            lines = ["%s  %s" % (time.strftime("%H:%M:%S", time.localtime(t)), s) for t, s in self.events[-n:]]
            lc = self.last_contact
        head = ("Last report from a turtle: %d s ago, from %s." % (time.time() - lc[0], lc[1] or "?")) if lc else \
               "No turtle has contacted this server yet."
        return head + "\n" + ("\n".join(lines) if lines else "(nothing has reached the server since it started)")

    def god_name(self, tid):
        """The next unused Deadlock hero name for a turtle (in this run's random order), one per turtle, remembered. After the list: "<name> 2"."""
        with self.lock:
            if tid in self.gods:
                return self.gods[tid]
            used = set(self.gods.values()) | {t.get("label") for t in self.turtles.values()}
            name = None
            for n in range(1, 100):
                for g in self.name_order:
                    cand = g if n == 1 else "%s %d" % (g, n)
                    if cand not in used:
                        name = cand
                        break
                if name:
                    break
            self.gods[tid] = name
        if self.on_anchor:
            self.on_anchor()
        return name

    # ---------------------------------------------------------------- commands
    RUN_NAME = re.compile(r"[a-z0-9_\-]{1,40}")

    def command(self, tid, cmd, arg=""):
        """Queue a command for a turtle; it gets it in the answer to its next report.
        "stop" ends its program; "run <program>" starts a program on an idle agent turtle."""
        t = self.turtles.get(tid)
        if t is None:
            return False
        if cmd == "stop":
            text = "stop"
        elif cmd == "run" and isinstance(arg, str) and self.RUN_NAME.fullmatch(arg) and t.get("kind") == "agent":
            text = "run " + arg
        else:
            return False
        with self.lock:
            self.cmds[tid] = text
        return True

    def take_command(self, tid):
        with self.lock:
            cmd = self.cmds.pop(tid, "")
            if cmd == "stop" and tid in self.turtles:
                self.turtles[tid]["stop_sent"] = True
        return cmd

    def reply_for(self, tid):
        """The answer to a report: ok [command], then where this turtle is and who is nearby (world coordinates)."""
        cmd = self.take_command(tid)
        lines = ["ok " + cmd if cmd else "ok"]
        with self.lock:
            me0 = self.turtles.get(tid)
            unnamed = me0 is not None and not me0.get("label")
        if unnamed:
            lines.append("label " + self.god_name(tid).replace(" ", "_"))
        target = self.goto.pop(tid, None) if cmd.startswith("run") else None
        if target:
            lines.append("goto %d %d %d %d" % target)
        now = time.time()
        with self.lock:
            me = self.turtles.get(tid)
            mine = self.world_pos(me) if me else None
            if mine:
                lines.append("me %d %d %d" % mine)
                near = []
                for oid, o in self.turtles.items():
                    wp = self.world_pos(o) if oid != tid and now - o["last_seen"] <= self.OFFLINE_AFTER else None
                    if wp:
                        d = abs(wp[0] - mine[0]) + abs(wp[1] - mine[1]) + abs(wp[2] - mine[2])
                        near.append((d, oid, re.sub(r"[^A-Za-z0-9_\-]", "_", o.get("label") or o.get("name") or "turtle")[:20], wp))
                for d, oid, nm, wp in sorted(near)[:6]:
                    lines.append("peer %d %s %d %d %d" % ((oid, nm) + wp))
        return "\n".join(lines)

    def _job_active(self, tid, job, now):
        t = self.turtles.get(tid)
        if t is None:
            return False
        if not job["running"]:
            return now - job["t"] < 900                           # sent, not started yet (travelling)
        return t.get("kind") != "agent" and self.state_of(t, now) not in ("finished", "stopped")

    def dispatch(self, slug, foot, site, facing):
        """Send a job to the nearest idle agent. site = world (x, y, z) of the job's start cell, facing = which way
        it faces there, foot = the job's footprint (local box) or None. Returns the turtle id; raises ValueError
        with a plain-words reason when it can't."""
        if not self.RUN_NAME.fullmatch(slug or ""):
            raise ValueError("That is not a valid program name.")
        if facing not in FACINGS:
            raise ValueError("Facing must be north, east, south or west.")
        site = tuple(int(v) for v in site)
        now = time.time()
        with self.lock:
            box = world_box(site + (facing,), foot) if foot else None
            if box:
                for jid, job in list(self.jobs.items()):
                    if self._job_active(jid, job, now):
                        if boxes_overlap(box, job["box"]):
                            raise ValueError("That would overlap '%s' that turtle #%d is working on." % (job["slug"], jid))
                    else:
                        del self.jobs[jid]
            best = None
            idle = 0
            for tid, t in self.turtles.items():
                if t.get("kind") != "agent" or self.state_of(t, now) != "idle" or tid in self.cmds or now - self.sent.get(tid, 0) < 20:
                    continue
                idle += 1
                a, wp = self._anchor(t), self.world_pos(t)
                if not a or not wp:
                    continue
                d = abs(wp[0] - site[0]) + abs(wp[1] - site[1]) + abs(wp[2] - site[2])
                if best is None or d < best[0]:
                    best = (d, tid, a)
            if best is None:
                raise ValueError("No idle agent turtle with a known position%s. Start the Agent program on a turtle and set its "
                                 "start position (or use GPS)." % (" (%d idle, but none placed)" % idle if idle else ""))
            _d, tid, a = best
            lx, ly, lz = world_to_local(a[:4], site)
            self.cmds[tid] = "run " + slug
            self.sent[tid] = now
            self.goto[tid] = (lx, ly, lz, facing_code(a[3], facing))
            self.next_anchor[tid] = site + (facing,)
            if box:
                self.jobs[tid] = {"slug": slug, "box": box, "t": now, "running": False}
            else:
                self.jobs.pop(tid, None)
        return tid

    # ---------------------------------------------------------------- stations (jobs with chests) and haulers
    def stations(self):
        """Names of the jobs that have chests, for the hauler's drop-down lists."""
        with self.lock:
            return sorted({t.get("name", "") for t in self.turtles.values() if t.get("kind") in STATION_CHESTS and t.get("name")})

    def _chest_stand(self, name, default_side):
        """World cell of the block above a station's chest, or (None, reason)."""
        base, _, side = (name or "").partition(":")
        side = side.strip().lower() or default_side
        base = base.strip().lower()
        if side not in ("in", "out"):
            return None, "side must be in or out"
        found = False
        for t in self.turtles.values():
            if t.get("name", "").lower() != base or t.get("kind") not in STATION_CHESTS:
                continue
            found = True
            cell = STATION_CHESTS[t["kind"]].get(side)
            a = self._anchor(t)
            if cell and a:
                w = local_to_world(a[:4], cell)
                return (w[0], w[1] + 1, w[2]), ""
        if found:
            return None, "'%s' has no known position (set its start position)" % name
        return None, "no job called '%s' has reported in" % name

    def route(self, tid, legs):
        """For a hauler: where to stand to take from / give to each leg's stations, in the hauler's own frame.
        Lines: 'leg N fx fy fz tx ty tz' or 'leg N ? reason'."""
        lines = []
        with self.lock:
            h = self.turtles.get(tid)
            a = self._anchor(h) if h else None
            for i, leg in enumerate(legs[:8], 1):
                if not a:
                    lines.append("leg %d ? the hauler's own start position is unknown" % i)
                    continue
                ends, why = [], ""
                for key, side in (("from", "out"), ("to", "in")):
                    w, why = self._chest_stand(str(leg.get(key, "")), side)
                    if w is None:
                        break
                    ends.append(world_to_local(a[:4], w))
                if why or len(ends) < 2:
                    lines.append("leg %d ? %s" % (i, why or "unknown"))
                else:
                    lines.append("leg %d %d %d %d %d %d %d" % ((i,) + tuple(ends[0]) + tuple(ends[1])))
        return "\n".join(lines)

    # ---------------------------------------------------------------- the foreman (sets up the other turtles)
    @staticmethod
    def _setup_jobs(jobs):
        """Validate the job list a foreman sends: [{name, slug, kind, furnaces, foot}]."""
        if not isinstance(jobs, list) or len(jobs) > 16:
            raise ValueError("bad job list")
        out = []
        for j in jobs:
            if not isinstance(j, dict) or not isinstance(j.get("name"), str) or not re.fullmatch(r"[A-Za-z0-9 _.:\-]{1,40}", j["name"]):
                raise ValueError("bad job name")
            if not isinstance(j.get("slug"), str) or not Fleet.RUN_NAME.fullmatch(j["slug"]):
                raise ValueError("bad program name")
            foot = j.get("foot")
            if foot is not None and not (isinstance(foot, list) and len(foot) == 6 and all(isinstance(v, int) for v in foot)):
                raise ValueError("bad footprint")
            fur = j.get("furnaces", 0)
            out.append({"name": j["name"], "slug": j["slug"], "kind": str(j.get("kind", "")), "foot": foot,
                        "furnaces": fur if isinstance(fur, int) and 0 <= fur <= 16 else 0})
        return out

    def _auto_site(self, ftid, job):
        """No position was given for this job: put it in a row to the right of the foreman, one footprint after the other."""
        key = job["name"].strip().lower()
        if key in self.planned or key in self.auto_sites:
            return
        a = self._anchor(self.turtles[ftid]) if ftid in self.turtles else None
        if not a:
            return
        foot = job.get("foot") or [-1, -1, -1, 1, 1, 1]
        cur = self.layout_cursor.get(ftid, 6)
        right = cur - foot[0]
        w = local_to_world(a[:4], (right, 0, 6))
        self.auto_sites[key] = (w[0], w[1], w[2], a[3])
        self.layout_cursor[ftid] = right + foot[3] + 1 + 3

    # v8.1: the Foreman's jobs are placed from the Foreman's own start cell. Typed coordinates in the Colony tab (an old, far away one sent a turtle 300 blocks off) are not used here.
    def _foreman_site(self, ftid, job):
        """Where a foreman's job goes: always an offset from the foreman itself (right and ahead of it, one footprint after the
        other with 10 blocks between), never a typed coordinate. Remembered per foreman start position."""
        a = self._anchor(self.turtles[ftid]) if ftid in self.turtles else None
        if not a:
            return None
        st = self.fsites.get(ftid)
        if not st or st["anchor"] != a[:4]:
            st = self.fsites[ftid] = {"anchor": a[:4], "cursor": 8, "sites": {}}
        key = job["name"].strip().lower()
        if key not in st["sites"]:
            foot = job.get("foot") or [-1, -1, -1, 1, 1, 1]
            right = st["cursor"] - foot[0]
            w = local_to_world(a[:4], (right, 0, 8))
            st["sites"][key] = (w[0], w[1], w[2], a[3])
            st["cursor"] = right + foot[3] + 1 + 10
        return st["sites"][key]

    def _job_site(self, name):
        """(x, y, z, facing) of a job's start cell by its name: the planned position, else the anchor of a turtle of that name."""
        key = name.strip().lower()
        if key in self.planned:
            return self.planned[key]
        if key in self.auto_sites:
            return self.auto_sites[key]
        for t in self.turtles.values():
            if (t.get("name") or "").strip().lower() == key:
                a = self._anchor(t)
                if a:
                    return a[:4]
        return None

    def setup_plan(self, tid, jobs):
        """For a foreman: the chests and furnaces to place, as cells to stand on (the foreman's own frame).
        Lines: 'chest NAME x y z', 'furnace NAME x y z', 'skip NAME reason', 'error reason'."""
        jobs = self._setup_jobs(jobs)
        lines = []
        with self.lock:
            f = self.turtles.get(tid)
            a = self._anchor(f) if f else None
            if not a:
                return "error my own start position is unknown (set it in the Fleet or Colony tab, or use GPS)"
            for j in jobs:
                cells = [("chest", c) for c in STATION_CHESTS.get(j["kind"], {}).values()]
                if j["kind"] == "smelter":
                    cells += [("furnace", (k, 0, 2)) for k in range(j["furnaces"])]
                if not cells:
                    continue
                site = self._foreman_site(tid, j)
                if not site:
                    lines.append("skip %s no start position yet" % j["name"])
                    continue
                for what, rel in cells:
                    w = local_to_world(site, rel)
                    lx, ly, lz = world_to_local(a[:4], (w[0], w[1] + 1, w[2]))
                    lines.append("%s %s %d %d %d" % (what, j["name"], lx, ly, lz))
        return "\n".join(lines) or "ok"

    def setup_spawn(self, tid, turtle_id, rel):
        """A foreman built a new turtle `rel` (right, up, forward) from its own start cell: the new turtle's start position is known
        from then on (it was placed facing the way the foreman faces)."""
        if not (isinstance(rel, list) and len(rel) == 3 and all(isinstance(v, int) for v in rel)) or not isinstance(turtle_id, int):
            raise ValueError("bad spawn")
        with self.lock:
            f = self.turtles.get(tid)
            a = self._anchor(f) if f else None
        if not a:
            raise ValueError("the foreman's own start position is unknown")
        w = local_to_world(a[:4], tuple(rel))
        self.set_anchor(turtle_id, w[0], w[1], w[2], a[3])
        return "ok"

    def setup_ready(self, turtle_id):
        """Has this new turtle started its agent program and reported in?"""
        with self.lock:
            t = self.turtles.get(turtle_id)
            ok = bool(t) and t.get("kind") == "agent" and self.state_of(t, time.time()) == "idle"
        return "ready" if ok else "wait"

    def setup_dispatch(self, tid, jobs):
        """For a foreman: hand every job to the nearest idle agent. Lines: 'sent NAME id' or 'fail NAME reason'."""
        jobs = self._setup_jobs(jobs)
        lines = []
        for j in jobs:
            with self.lock:
                site = self._foreman_site(tid, j)
            if not site:
                lines.append("fail %s no start position" % j["name"])
                continue
            try:
                lines.append("sent %s %d" % (j["name"], self.dispatch(j["slug"], j["foot"], site[:3], site[3])))
            except ValueError as e:
                lines.append("fail %s %s" % (j["name"], str(e)[:60]))
        return "\n".join(lines) or "ok"

    # ---------------------------------------------------------------- storage keepers
    _ITEM = re.compile(r"[a-z0-9_:.\-]{1,60}$")

    def report_storage(self, p):
        """What a storage keeper holds (POST /storage). Answers with the orders waiting for it: 'order <count> <item>' lines."""
        if not isinstance(p, dict) or p.get("v") != 1 or not isinstance(p.get("id"), int) or not isinstance(p.get("items"), dict):
            raise ValueError("not a storage report")
        items = {}
        for k, v in list(p["items"].items())[:2000]:
            if isinstance(k, str) and self._ITEM.match(k) and isinstance(v, (int, float)) and 0 < v < 10 ** 9:
                items[k] = int(v)
        with self.lock:
            self.storage[p["id"]] = {"id": p["id"], "name": _clip(p.get("name"), 60), "items": items, "seen": time.time(),
                                     "chests": _num(p.get("chests")), "max": _num(p.get("max")), "stacks": _num(p.get("stacks")),
                                     "slots": _num(p.get("slots")), "spare": _num(p.get("spare"))}
            todo = self.orders.pop(p["id"], [])
        return "\n".join("order %d %s" % (c, i) for i, c in todo) or "ok"

    def storage_view(self):
        """For the web page: every keeper, and the items of all of them added up."""
        now = time.time()
        with self.lock:
            keepers, total = [], {}
            for tid, st in sorted(self.storage.items()):
                keepers.append({"id": tid, "name": st["name"], "chests": st["chests"], "max": st["max"], "stacks": st["stacks"],
                                "slots": st["slots"], "spare": st["spare"], "age": round(now - st["seen"], 1),
                                "waiting": len(self.orders.get(tid, []))})
                for item, c in st["items"].items():
                    e = total.setdefault(item, {"item": item, "count": 0, "keepers": {}})
                    e["count"] += c
                    e["keepers"][str(tid)] = c
            return {"keepers": keepers, "items": sorted(total.values(), key=lambda e: e["item"])}

    def order_item(self, item, count, keeper=None):
        """Ask a keeper to put `count` of `item` in its pickup chest (POST /order)."""
        if not isinstance(item, str) or not self._ITEM.match(item):
            raise ValueError("bad item")
        try:
            count = int(count)
        except (TypeError, ValueError):
            raise ValueError("bad count")
        if not 1 <= count <= 4096:
            raise ValueError("count must be between 1 and 4096")
        with self.lock:
            best = None
            for tid, st in self.storage.items():
                have = st["items"].get(item, 0)
                if keeper is not None and tid != keeper:
                    continue
                if have > 0 and (best is None or have > best[0]):
                    best = (have, tid)
            if best is None:
                raise ValueError("nothing like that is in storage")
            q = self.orders.setdefault(best[1], [])
            if len(q) >= 40:
                raise ValueError("that keeper has too many orders waiting")
            q.append((item, min(count, best[0])))
            return best[1]

    def forget(self, tid):
        with self.lock:
            self.storage.pop(tid, None)
            self.orders.pop(tid, None)
            self.turtles.pop(tid, None)
            self.cmds.pop(tid, None)
            self.goto.pop(tid, None)
            self.next_anchor.pop(tid, None)
            self.jobs.pop(tid, None)

    @staticmethod
    def state_of(t, now):
        msg = t.get("msg", "")
        if msg.startswith("Stopped"):
            return "stopped"
        if t.get("done"):
            return "finished"
        if now - t["last_seen"] > Fleet.OFFLINE_AFTER:
            return "offline"
        if t.get("stop_sent"):
            return "stopping"
        if msg.startswith("Error"):
            return "error"
        if t.get("kind") == "agent" and msg.startswith("Idle"):
            return "idle"
        if _ATTENTION.search(msg):
            return "attention"
        return "working"

    @staticmethod
    def _compass(anchor, code):
        """The world direction a turtle faces now: code is its own direction (1 = the way its start faced, 2 = right, 3 = back, 4 = left)."""
        if not anchor or code not in (1, 2, 3, 4):
            return ""
        order = ["north", "east", "south", "west"]
        return order[(order.index(anchor[3]) + int(code) - 1) % 4]

    def snapshot(self, now=None):
        now = time.time() if now is None else now
        with self.lock:
            rows = []
            for tid in sorted(self.turtles):
                t = self.turtles[tid]
                a = self._anchor(t)
                wp = self.world_pos(t)
                rows.append({"id": tid, "label": t.get("label", ""), "name": t.get("name", ""), "kind": t.get("kind", ""),
                             "x": t.get("x", 0), "y": t.get("y", 0), "z": t.get("z", 0), "fuel": t.get("fuel", ""),
                             "msg": t.get("msg", ""), "act": t.get("act", ""), "dir": self._compass(a, t.get("lf")),
                             "n": t.get("n", 0), "total": t.get("total", 0),
                             "state": self.state_of(t, now), "age": round(now - t["last_seen"], 1),
                             "world": list(wp) if wp else None, "anchor": a[4] if a else "",
                             "facing": a[3] if a else ""})
                if t.get("inv") is not None:
                    rows[-1]["inv"] = t["inv"]
                if t.get("q") is not None:
                    rows[-1]["q"] = t["q"]
                if t.get("crafty") or t.get("kind") == "foreman":
                    rows[-1]["crafty"] = True
            # v7.8: two turtles with the same name get (1), (2) so they can be told apart on the page.
            seen = {}
            for r in rows:                                      # two turtles with the same name: number them so they can be told apart
                seen.setdefault((r["label"] or r["name"]).lower(), []).append(r)
            for group in seen.values():
                if len(group) > 1:
                    for i, r in enumerate(group, 1):
                        r["label"] = "%s (%d)" % (r["label"] or r["name"], i)
        return rows
