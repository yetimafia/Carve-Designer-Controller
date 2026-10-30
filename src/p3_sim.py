# The route simulator (what the turtle will do, in order) and the small web server (LiveServer) the turtles talk to.
# Why together: the 3D viewer, the fleet page and the turtles all read the same simulated/live state.
# ============================================================ route simulator & view state
# Directions as the turtle numbers them: 1=+z (forward) 2=+x (right) 3=-z 4=-x 5=up 6=down
DX = (0, 1, 0, -1, 0, 0)
DZ = (1, 0, -1, 0, 0, 0)
DY = (0, 0, 0, 0, 1, -1)


class Sim:
    """Result of replaying the turtle's routine on a design.

    events: ('t', face) a turn | ('d', x, y, z) a block dug | ('m', x, y, z) a move
            | ('p', x, y, z) a block / torch placed
    """

    def __init__(self):
        self.events = []
        self.moves = self.digs = self.turns = self.places = 0
        self.total = 0

    @property
    def seconds(self):
        return (self.moves + self.digs + self.turns + self.places) * ACTION_SECONDS


def simulate(design):
    """Replay the turtle program's exact routine (same dig pattern, same path search, same torches).

    It assumes an ideal world: every block breaks, no mobs, the turtle always has the items it
    places, and it never has to stop to empty its inventory (that depends on what it digs up).
    """
    run, total, _skipped = build_run(design)
    sim = Sim()
    sim.total = total
    start = design.turtle
    w, d, h = design.w, design.d, design.h
    pattern, tmode = design.pattern, design.torch_mode
    targets = build_place(design)                       # cell -> slot
    torch_cells = {c for c, sl in targets.items() if "torch" in design.inv[sl]}
    mined = {start}
    placed = set()
    heap = []                                   # (rank, cell): unmined cells next to dug-out ones
    in_heap = set()
    dropped = set()
    pos = start
    face = 1
    ev = sim.events

    def inside(c):
        return 1 <= c[0] <= w and 1 <= c[1] <= h and 1 <= c[2] <= d

    def idx(c):
        return ((c[1] - 1) * d + (c[2] - 1)) * w + c[0]

    def nb(c, k):                                       # neighbour of c in direction k (1..6)
        return (c[0] + DX[k - 1], c[1] + DY[k - 1], c[2] + DZ[k - 1])

    def turn_to(f):
        nonlocal face
        diff = (f - face) % 4
        if diff == 0:
            return
        for s in {1: (1,), 2: (1, 1), 3: (-1,)}[diff]:       # right, right+right, or one left
            face = (face - 1 + s) % 4 + 1
            ev.append(("t", face))
            sim.turns += 1

    def has_work(c):
        for k in range(1, 7):
            n = nb(c, k)
            if n in run and n not in mined:
                return True
        return False

    def bfs(goal):
        order = (face, face % 4 + 1, (face + 1) % 4 + 1, (face + 2) % 4 + 1, 5, 6)
        par = {pos: None}
        pdir = {}
        queue_ = collections.deque([pos])
        while queue_:
            c = queue_.popleft()
            if goal(c):
                path = []
                while par[c] is not None:
                    path.append(pdir[c])
                    c = par[c]
                path.reverse()
                return path
            for k in order:
                n = nb(c, k)
                if n not in par and n in mined and n not in placed and inside(n):
                    par[n] = c
                    pdir[n] = k
                    queue_.append(n)
        return None

    def step(k):
        nonlocal pos
        if k <= 4:
            turn_to(k)
        pos = nb(pos, k)
        ev.append(("m",) + pos)
        sim.moves += 1

    # ---- dig pattern: where a cell comes in the order (mirrors rankOf in the turtle program)
    def outward(v, v0, mx):
        return v - v0 if v >= v0 else mx - v

    def rank(c):
        x, y, z = c
        if pattern == "lanes":
            rel = y - design.ty
            b = (rel + 1) // 3
            up = (h - design.ty + 1) // 3
            br = b if b >= 0 else up - b
            mid = design.ty + 3 * b
            v = 0 if y == mid else (1 if y == mid + 1 else 2)
            xl = w - x
            zr = (z - 1) if xl % 2 == 0 else (d - z)
            return ((br * w + xl) * d + zr) * 3 + v
        lr = outward(y, design.ty, h)
        ri = outward(z, design.tz, d)
        xr = (w - x) if ri % 2 == 0 else (x - 1)
        return (lr * d + ri) * w + xr

    def frontier_add(n):
        for k in range(1, 7):
            m = nb(n, k)
            if m in run and m not in mined and m not in in_heap:
                in_heap.add(m)
                dropped.discard(m)
                heapq.heappush(heap, (rank(m), m))

    def min_frontier():
        while heap:
            n = heap[0][1]
            if n not in mined and n not in dropped and any(
                    nb(n, k) in mined and nb(n, k) not in placed for k in range(1, 7)):
                return n
            heapq.heappop(heap)
            in_heap.discard(n)
        return None

    # ---- torches
    def can_block(n):
        want = len(run - placed - {n})
        seen = {start}
        stack = [start]
        while stack:
            c = stack.pop()
            for k in range(1, 7):
                m = nb(c, k)
                if m not in seen and m != n and m in run and m not in placed:
                    seen.add(m)
                    stack.append(m)
        if len(seen) != want:
            return False
        open_cells = {c for c in mined if c not in placed and c != n}
        seen = {start}
        stack = [start]
        while stack:
            c = stack.pop()
            for k in range(1, 7):
                m = nb(c, k)
                if m not in seen and m in open_cells:
                    seen.add(m)
                    stack.append(m)
        return len(seen) == len(open_cells)

    def place_now(n):
        placed.add(n)
        ev.append(("p",) + n)
        sim.places += 1

    # torches are dropped straight down from the cell above (see putTorch in the turtle program)
    torch_list = sorted(torch_cells, key=idx)
    deferred = set()

    def spot(n):
        return (n[0], n[1] + 1, n[2])

    def support_ready(n):
        b = (n[0], n[1] - 1, n[2])
        if not inside(b) or b not in run:
            return True
        sl = targets.get(b)
        if sl is not None and "torch" not in design.inv[sl]:
            return b in placed
        return False

    def torch_ready(n):
        return n not in placed and n not in deferred and support_ready(n)

    def put_torch(n):
        a = spot(n)
        for k in bfs(lambda c, g=a: c == g) or []:
            step(k)
        if n in run and n not in mined:
            dig_cell(n, 6)
        if n not in mined:
            return
        if not can_block(n):
            deferred.add(n)
            return
        place_now(n)

    def dig_cell(n, k):
        if k <= 4:
            turn_to(k)
        mined.add(n)
        ev.append(("d",) + n)
        sim.digs += 1
        frontier_add(n)
        return True

    def wanted(n):
        return n in run and n not in mined

    def dig_neighbors():
        order = [5, 6] + [(face - 1 + k) % 4 + 1 for k in range(4)]
        for k in order:
            n = nb(pos, k)
            if wanted(n):
                dig_cell(n, k)

    def dig_vertical():
        for k in (5, 6):
            n = nb(pos, k)
            if wanted(n):
                dig_cell(n, k)

    def dig_target(t):
        def goal(c):
            return any(nb(c, k) == t for k in range(1, 7))
        path = bfs(goal)
        if path is None:
            return None
        for k in path:
            step(k)
        for k in range(1, 7):
            if nb(pos, k) == t:
                return dig_cell(t, k)
        return None

    mission = None

    def find_mission():
        spot_of = {}
        for n in torch_list:
            if torch_ready(n):
                a = spot(n)
                if (a in mined or wanted(a)) and a not in placed:
                    spot_of[a] = n
        if not spot_of:
            return None
        par = {}
        queue_ = collections.deque()
        for c in sorted((c for c in mined if c not in placed), key=idx):
            par[c] = None
            queue_.append(c)
            if c in spot_of:
                return {"path": [], "n": spot_of[c]}
        while queue_:
            c = queue_.popleft()
            for k in range(1, 7):
                n = nb(c, k)
                if n not in par and inside(n) and wanted(n):
                    par[n] = c
                    if n in spot_of:
                        rev = []
                        cur = n
                        while par[cur] is not None:
                            rev.append(cur)
                            cur = par[cur]
                        rev.reverse()
                        return {"path": rev, "n": spot_of[n]}
                    queue_.append(n)
        return None

    def mission_step():
        nonlocal mission
        if tmode != "first" or not torch_list:
            return False
        if mission:
            while mission["path"] and not wanted(mission["path"][0]):
                mission["path"].pop(0)
            if not torch_ready(mission["n"]):
                mission = None
        if mission is None:
            mission = find_mission()
        if mission is None:
            return False
        if mission["path"]:
            if dig_target(mission["path"][0]) is None:
                mission = None
                return False
        else:
            n = mission["n"]
            mission = None
            a = spot(n)
            if a in mined and a not in placed:
                put_torch(n)
        return True

    def ready_step():
        if tmode != "early" or not torch_list:
            return False
        spots = {}
        for n in torch_list:
            if n in mined and torch_ready(n):
                a = spot(n)
                if a in mined and a not in placed:
                    spots[a] = n
        if not spots:
            return False
        path = bfs(lambda c: c in spots)
        if path is None:
            return False
        for k in path:
            step(k)
        put_torch(spots[pos])
        return True

    def nearest_step():
        dig_neighbors()
        path = bfs(has_work)
        if not path:
            return False
        for k in path:
            step(k)
        return True

    def ordered_step():
        if pattern == "lanes":
            dig_vertical()
        t = min_frontier()
        if t is None:
            return False
        if dig_target(t) is None:
            dropped.add(t)
        return True

    # ---- dig everything
    frontier_add(start)
    ordered = pattern != "nearest"
    guard = 0
    while True:
        if not mission_step() and not ready_step():
            if ordered:
                if not ordered_step():
                    break
            elif not nearest_step():
                break
        guard += 1
        if guard > 400000:
            break
    if ordered:
        while nearest_step():
            guard += 1
            if guard > 400000:
                break

    # ---- place whatever is still waiting (blocks, and torches that couldn't go in earlier),
    # farthest from the start first so the way home stays open
    if targets:
        dist = {start: 0}
        queue_ = collections.deque([start])
        while queue_:
            c = queue_.popleft()
            for k in range(1, 7):
                n = nb(c, k)
                if n not in dist and n in mined and n not in placed and inside(n):
                    dist[n] = dist[c] + 1
                    queue_.append(n)
        order = sorted((c for c in targets if c in dist and c != start and c not in placed
                        and c not in torch_cells),
                       key=lambda c: (-dist[c], idx(c)))
        for t in order:
            stand = None
            for k in range(1, 7):                                   # same direction order as the turtle
                a = (t[0] - DX[k - 1], t[1] - DY[k - 1], t[2] - DZ[k - 1])
                if inside(a) and dist.get(a) == dist[t] - 1:
                    stand, kdir = a, k
                    break
            if stand is None:
                continue
            for k in bfs(lambda c, g=stand: c == g) or []:
                step(k)
            if kdir <= 4:
                turn_to(kdir)
            place_now(t)
    if torch_list:                                              # torches that had to wait for their floor
        dist = {start: 0}
        queue_ = collections.deque([start])
        while queue_:
            c = queue_.popleft()
            for k in range(1, 7):
                n = nb(c, k)
                if n not in dist and n in mined and n not in placed and inside(n):
                    dist[n] = dist[c] + 1
                    queue_.append(n)
        todo = [n for n in torch_list if n in mined and n not in placed and support_ready(n) and spot(n) in dist]
        todo.sort(key=lambda n: (-dist[spot(n)], idx(n)))
        for n in todo:
            path = bfs(lambda c, g=spot(n): c == g)
            if path is None:
                continue
            for k in path:
                step(k)
            place_now(n)
    home = bfs(lambda c: c == start)
    if home is not None:
        for k in home:
            step(k)
        if design.chest:
            turn_to(3)
        turn_to(1)
    return sim


class ViewState:
    """What the viewer shows: which cells are dug, where the turtle is, where it has been."""

    def __init__(self, design):
        self.design = design
        self.mined = {design.turtle}
        self.pos = design.turtle
        self.face = 1
        self.trail = collections.deque([design.turtle], maxlen=300)
        self.moves = 0
        self.turns = 0
        self.placed = set()

    def apply(self, ev):
        k = ev[0]
        if k == "t":
            self.face = ev[1]
            self.turns += 1
        elif k == "d":
            self.mined.add(ev[1:])
        elif k == "p":
            self.placed.add(ev[1:])
        else:
            self.pos = ev[1:]
            self.trail.append(self.pos)
            self.moves += 1


# =================================================================== live view
class LiveSession:
    """Everything one turtle has reported to us."""

    def __init__(self, turtle_id):
        self.id = turtle_id
        self.design = None
        self.view = None
        self.name = ""
        self.count = 0
        self.total = 0
        self.fuel = ""
        self.msg = ""
        self.done = False
        self.stopped = False
        self.placed_count = self.placed_total = 0
        self.last_seen = 0.0
        self.waiting_for_sync = True
        self.new_design = False          # set when the design object was replaced

    def apply(self, p):
        """Fold one report into the session. Raises ValueError on nonsense."""
        if not isinstance(p, dict) or p.get("v") != 1:
            raise ValueError("not a Carve report")
        w, d, h = int(p["w"]), int(p["d"]), int(p["h"])
        if "layers" in p:                                   # full picture (start, resume, every 30 s)
            des = design_from_flat(p.get("name", ""), w, d, h, (p["tx"], p["ty"], p["tz"]),
                                   p.get("chest", True), p["layers"], str(p.get("place", "")),
                                   p.get("inv") or None)
            full = str(p.get("full", ""))
            if len(full) != w * d * h:
                raise ValueError("bad progress data")
            same = (self.design is not None and self.design.to_json() == des.to_json())
            if not same:
                self.design = des
                self.view = ViewState(des)
                self.new_design = True
            mined = {des.turtle}
            for i, ch in enumerate(full):
                if ch == "1":
                    mined.add(cell_from_index(i + 1, w, d))
            self.view.mined = mined
            placed = str(p.get("placed", ""))
            if placed and len(placed) != w * d * h:
                raise ValueError("bad progress data")
            self.view.placed = {cell_from_index(i + 1, w, d) for i, ch in enumerate(placed) if ch == "1"}
            self.waiting_for_sync = False
        if self.design is None:
            return False                                    # joined mid-run; wait for the next full picture
        for i in p.get("cells", []):
            self.view.mined.add(cell_from_index(int(i), w, d))
        for i in p.get("pl", []):
            self.view.placed.add(cell_from_index(int(i), w, d))
        self.placed_count, self.placed_total = int(p.get("pc", 0)), int(p.get("pt", 0))
        path = p.get("path", [])
        for j in range(0, len(path) - 2, 3):
            c = (int(path[j]), int(path[j + 1]), int(path[j + 2]))
            self.view.pos = c
            self.view.trail.append(c)
            self.view.moves += 1
        self.view.pos = (int(p["x"]), int(p["y"]), int(p["z"]))
        self.view.face = int(p.get("f", 1))
        self.name = str(p.get("name", ""))
        self.count, self.total = int(p.get("mined", 0)), int(p.get("total", 0))
        self.fuel, self.msg = str(p.get("fuel", "")), str(p.get("msg", ""))
        self.done = bool(p.get("done", False))
        self.stopped = bool(p.get("stopped", False))
        self.last_seen = time.time()
        return True


class LiveServer:
    """A tiny local web server the turtle POSTs its progress to."""

    def __init__(self, host, port, on_payload, fleet=None):
        self.host, self.port, self.on_payload, self.fleet = host, port, on_payload, fleet
        self.httpd = None
        self.thread = None

    def start(self):
        on_payload, fleet = self.on_payload, self.fleet

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _reply(self, code, text):
                raw = text.encode("utf-8")
                self.send_response(code)
                self.send_header("Content-Type", "text/plain; charset=utf-8")
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

            def do_GET(self):
                path = self.path.split("?")[0]
                if fleet is not None and path == "/debug":
                    return self._reply(200, fleet.debug_text(60))
                if fleet is not None and path == "/":
                    fleet.note("web page opened from %s" % self.client_address[0])
                if fleet is not None and path in ("/three.min.js", "/turtle3d.js"):
                    raw = (three_source() if path == "/three.min.js" else TURTLE3D_JS).encode("utf-8")
                    self.send_response(200)
                    self.send_header("Content-Type", "application/javascript; charset=utf-8")
                    self.send_header("Cache-Control", "max-age=3600")
                    self.send_header("Content-Length", str(len(raw)))
                    self.end_headers()
                    self.wfile.write(raw)
                    return
                if fleet is not None and path == "/icons":
                    # item pictures for the web page: your imported textures first, our simplified vanilla tiles next, nothing for
                    # modded items without a texture (the page draws those as a solid colour)
                    q = urllib.parse.parse_qs(self.path.partition("?")[2])
                    out = {}
                    for nm in (q.get("names", [""])[0].split(","))[:160]:
                        if not re.fullmatch(r"[a-z0-9_.\-]+:[a-z0-9_./\-]+", nm or "") or len(nm) > 90:
                            continue
                        try:
                            t = pack_tile(nm) or item_tile(nm)
                        except Exception:
                            t = None
                        if t:
                            out[nm] = _pack_encode(t)
                    raw = json.dumps(out).encode("utf-8")
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Cache-Control", "no-store")
                    self.send_header("Content-Length", str(len(raw)))
                    self.end_headers()
                    self.wfile.write(raw)
                    return
                if fleet is not None and path == "/map3d":
                    q = urllib.parse.parse_qs(self.path.partition("?")[2])

                    def qn(k, d, lo, hi):
                        try:
                            return max(lo, min(hi, int(q.get(k, [d])[0])))
                        except ValueError:
                            return d
                    names, cells, cut = fleet.world.view3d(qn("cx", 0, -3 * 10 ** 7, 3 * 10 ** 7), qn("cy", 64, -2048, 2048),
                                                           qn("cz", 0, -3 * 10 ** 7, 3 * 10 ** 7), qn("r", 40, 4, 120), qn("ry", 40, 2, 200))
                    raw = json.dumps({"names": names, "cells": cells, "truncated": cut, "count": fleet.world.count,
                                      "turtles": [r for r in fleet.snapshot() if r["world"]]}).encode("utf-8")
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Cache-Control", "no-store")
                    self.send_header("Content-Length", str(len(raw)))
                    self.end_headers()
                    self.wfile.write(raw)
                    return
                if fleet is not None and path in ("/", "/fleet", "/map", "/storage"):
                    if path == "/":
                        raw = FLEET_HTML.encode("utf-8")
                        ctype = "text/html; charset=utf-8"
                    elif path == "/fleet":
                        raw = json.dumps({"turtles": fleet.snapshot()}).encode("utf-8")
                        ctype = "application/json"
                    elif path == "/storage":
                        raw = json.dumps(fleet.storage_view()).encode("utf-8")
                        ctype = "application/json"
                    else:
                        q = urllib.parse.parse_qs(self.path.partition("?")[2])

                        def qi(k, d, lo, hi):
                            try:
                                return max(lo, min(hi, int(q.get(k, [d])[0])))
                            except ValueError:
                                return d
                        names, cells = fleet.world.view(qi("cx", 0, -3 * 10 ** 7, 3 * 10 ** 7), qi("cz", 0, -3 * 10 ** 7, 3 * 10 ** 7),
                                                        qi("r", 40, 4, 120), "slice" if q.get("mode", [""])[0] == "slice" else "top",
                                                        qi("y", 64, -2048, 2048))
                        raw = json.dumps({"names": names, "cells": cells, "count": fleet.world.count,
                                          "turtles": [r for r in fleet.snapshot() if r["world"]],
                                          "waiting": fleet.map_waiting()}).encode("utf-8")
                        ctype = "application/json"
                    self.send_response(200)
                    self.send_header("Content-Type", ctype)
                    self.send_header("Cache-Control", "no-store")
                    self.send_header("Content-Length", str(len(raw)))
                    self.end_headers()
                    self.wfile.write(raw)
                    return
                self._reply(200, "Carve Designer live view is listening.\n")

            def do_POST(self):
                path = self.path.split("?")[0]
                ip = self.client_address[0]
                try:
                    n = int(self.headers.get("Content-Length", "0"))
                    if n <= 0 or n > 8 * 1024 * 1024:
                        if fleet is not None:
                            fleet.note("rejected %s from %s: bad size" % (path, ip))
                        return self._reply(400, "bad size")
                    data = json.loads(self.rfile.read(n).decode("utf-8"))
                except Exception:
                    if fleet is not None:
                        fleet.note("rejected %s from %s: not JSON" % (path, ip))
                    return self._reply(400, "bad request")
                if fleet is not None and isinstance(data, dict):
                    who = "turtle %s%s" % (data.get("id", "?"), (" '%s'" % data["name"]) if data.get("name") else "")
                    fleet.note("%s from %s: %s" % (path, ip, who) + (" - " + str(data.get("msg"))[:60] if data.get("msg") else ""),
                               turtle=path in ("/status", "/update", "/map", "/storage", "/route", "/setup"), addr=ip)
                if fleet is not None and path in ("/cmd", "/forget"):
                    tid = data.get("id") if isinstance(data, dict) else None
                    if not isinstance(tid, int):
                        return self._reply(400, "bad id")
                    if path == "/forget":
                        fleet.forget(tid)
                        return self._reply(200, "ok")
                    return self._reply(200 if fleet.command(tid, data.get("cmd"), data.get("arg", "")) else 400, "ok")
                if fleet is not None and path == "/storage":
                    try:
                        return self._reply(200, fleet.report_storage(data))
                    except ValueError:
                        return self._reply(400, "bad storage report")
                if fleet is not None and path == "/order":
                    try:
                        tid = fleet.order_item(data.get("item"), data.get("count"), data.get("keeper") if isinstance(data.get("keeper"), int) else None)
                    except (ValueError, AttributeError) as e:
                        return self._reply(400, str(e))
                    return self._reply(200, "ok %d" % tid)
                if path == "/setup" and fleet is not None:
                    try:
                        if not isinstance(data.get("id"), int) or data.get("action") not in ("plan", "dispatch", "spawn", "ready"):
                            raise ValueError("bad setup request")
                        if data["action"] == "spawn":
                            return self._reply(200, fleet.setup_spawn(data["id"], data.get("turtle"), data.get("rel")))
                        if data["action"] == "ready":
                            return self._reply(200, fleet.setup_ready(data.get("turtle")))
                        fn = fleet.setup_plan if data["action"] == "plan" else fleet.setup_dispatch
                        return self._reply(200, fn(data["id"], data.get("jobs")))
                    except ValueError as e:
                        return self._reply(400, str(e))
                if path == "/route" and fleet is not None:
                    legs = data.get("legs") if isinstance(data, dict) else None
                    if not isinstance(data.get("id"), int) or not isinstance(legs, list) or not all(isinstance(l, dict) for l in legs):
                        return self._reply(400, "bad route request")
                    return self._reply(200, fleet.route(data["id"], legs))
                if path == "/map":
                    try:
                        if fleet is None:
                            raise ValueError("fleet off")
                        fleet.report_map(data)
                    except ValueError:
                        return self._reply(400, "bad report")
                    return self._reply(200, "ok")
                if path == "/status":
                    try:
                        if fleet is None:
                            raise ValueError("fleet off")
                        fleet.report_status(data)
                    except ValueError:
                        return self._reply(400, "bad report")
                else:
                    on_payload(data)
                    if fleet is not None:
                        fleet.report_update(data)
                tid = data.get("id") if isinstance(data, dict) else None
                self._reply(200, fleet.reply_for(tid) if fleet is not None and isinstance(tid, int) else "ok")

        self.httpd = ThreadingHTTPServer((self.host, self.port), Handler)
        self.httpd.daemon_threads = True
        self.port = self.httpd.server_address[1]
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()

    def stop(self):
        if self.httpd:
            self.httpd.shutdown()
            self.httpd.server_close()
            self.httpd = None
