# The design model: a grid of cells (what to dig / place), the turtle's 16 item slots and the file format that is saved
# and uploaded. Everything else (simulator, GUI, GitHub) works on these objects.
# Why it is first: the other parts are glued together in the order build.py lists them, and they all need the model.
# ======================================================================= model
def slugify(name):
    """Short, file-safe name used for the program's file name in the repo."""
    s = re.sub(r"[^a-z0-9]+", "_", (name or "").lower()).strip("_")
    return s[:30].strip("_") or "design"


def clean_name(name):
    name = re.sub(r"[^A-Za-z0-9 _.,:()\-]", "", name or "").strip()
    return name[:30] or "Carve job"


# Items the turtle can carry for placing. (name, colour shown in the designer)
ITEM_PRESETS = [
    ("minecraft:torch", "#fff35c"), ("minecraft:lantern", "#ffb347"), ("minecraft:glowstone", "#ffd54a"),
    ("minecraft:sea_lantern", "#bdf7ee"), ("minecraft:cobblestone", "#9aa0a6"), ("minecraft:stone", "#7d8590"),
    ("minecraft:stone_bricks", "#6b7280"), ("minecraft:smooth_stone", "#aeb4bb"),
    ("minecraft:cobbled_deepslate", "#4b5058"), ("minecraft:deepslate_bricks", "#3d4046"),
    ("minecraft:bricks", "#c0504d"), ("minecraft:sandstone", "#e8d9a0"), ("minecraft:oak_planks", "#c8a165"),
    ("minecraft:spruce_planks", "#7a5a37"), ("minecraft:dirt", "#8b5a2b"), ("minecraft:glass", "#a5f3fc"),
    ("minecraft:iron_bars", "#c8ccd0"), ("minecraft:ladder", "#b08850"), ("minecraft:chest", "#d9822b"),
]
PATTERNS = [("nearest", "Nearest first (the original way)"),
            ("rows", "Rows: right to left, then forward"),
            ("lanes", "3-high lanes: up, ahead, down")]
TORCH_MODES = [("first", "Torches first (tunnel to them)"),
               ("early", "As soon as their cell is dug"),
               ("end", "After everything is dug")]
DEFAULT_FAVORITES = ["minecraft:torch", "minecraft:cobblestone", "minecraft:stone_bricks", "minecraft:glass"]
MAX_SUPPLY_SLOTS = 8        # the turtle needs the other slots for what it digs up
SLOT_CHARS = "0123456789abcdefg"       # slot 1-16 as one character (0 = none), same as the turtle program
TORCH = "minecraft:torch"


def clean_item(name):
    """'torch' / 'Minecraft:Torch' -> 'minecraft:torch'; None when it isn't a usable item id."""
    name = (name or "").strip().lower().replace(" ", "_")
    if not name:
        return None
    if ":" not in name:
        name = "minecraft:" + name
    if len(name) > 60 or ".." in name or not re.fullmatch(r"[a-z0-9_.\-]+:[a-z0-9_/.\-]+", name):
        return None
    return name


def item_label(name):
    return name.split(":", 1)[-1].replace("_", " ")


def item_color(name):
    st = icon_stats(name)                      # vanilla items: the colour measured from the game
    if st is not None:
        return "#%02x%02x%02x" % st[1]
    for n, col in ITEM_PRESETS:
        if n == name:
            return col
    h = sum((i + 1) * ord(ch) for i, ch in enumerate(name)) % 360       # stable colour for modded items
    r, g, b = colorsys.hsv_to_rgb(h / 360.0, 0.45, 0.95)
    return "#%02x%02x%02x" % (int(r * 255), int(g * 255), int(b * 255))


SKINS = [("crafty", "Crafty turtle"), ("classic", "Green turtle"), ("bee", "Bee"), ("sea", "Sea turtle"),
         ("golem", "Iron golem"), ("custom", "Custom colours")]
SKIN_COLORS = {"crafty": "#aab0ba", "classic": "#7ddc4a", "bee": "#f5c518", "sea": "#3a9d5a", "golem": "#c9c9c4"}


MARK_FACES = ("forward", "right", "back", "left")


class Design:
    """Cells are (x, y, z), 1-based. x = right, y = up (layer), z = forward.

    sel   - cells to dig out
    inv   - turtle slot (1-16) -> item the turtle keeps in that slot for placing
    place - cell -> slot: after this cell is dug out, put that slot's item into it
    """
    def __init__(self, w=9, d=9, h=4):
        self.w, self.d, self.h = w, d, h
        self.tx, self.ty, self.tz = 1, 1, 1      # where the turtle stands
        self.chest = True
        self.sel = set()
        self.inv = {}
        self.place = {}
        self.pattern = "nearest"        # which order the cells are dug in
        self.torch_mode = "first"       # when torches go in
        self.seal = False               # plug lava / water above and below with spare blocks
        self.skin = "crafty"            # how the turtle looks in the previews
        self.skin_body, self.skin_accent = "#6fe36f", "#1c7c3c"     # colours of the "custom" skin
        self.name = "Carve job"
        self.marks = {}                 # base design: station name -> (x, y, z, face), face = forward / right / back / left of the design

    def copy(self):
        c = Design(self.w, self.d, self.h)
        c.tx, c.ty, c.tz, c.chest, c.name = self.tx, self.ty, self.tz, self.chest, self.name
        c.sel = set(self.sel)
        c.marks = dict(self.marks)
        c.inv = dict(self.inv)
        c.place = dict(self.place)
        c.pattern, c.torch_mode, c.seal = self.pattern, self.torch_mode, self.seal
        c.skin, c.skin_body, c.skin_accent = self.skin, self.skin_body, self.skin_accent
        return c

    def inside(self, x, y, z):
        return 1 <= x <= self.w and 1 <= y <= self.h and 1 <= z <= self.d

    @property
    def turtle(self):
        return (self.tx, self.ty, self.tz)

    @property
    def chest_cell(self):
        """The cell directly behind the turtle (only inside the grid if tz > 1)."""
        return (self.tx, self.ty, self.tz - 1) if self.tz > 1 else None

    def slug(self):
        return slugify(self.name)

    def set_cell(self, x, y, z, on, slot=None):
        """Select / unselect a cell. `slot` (with on=True) also says what to place there afterwards;
        on=True without a slot means "just dig it" and forgets any block assigned before."""
        c = (x, y, z)
        if c == self.turtle or not self.inside(x, y, z):
            return
        if on:
            self.sel.add(c)
            if slot is not None and slot in self.inv:
                self.place[c] = slot
            else:
                self.place.pop(c, None)
        else:
            self.sel.discard(c)
            self.place.pop(c, None)

    def cell_state(self, c):
        """(dug?, slot to place or None) - what a brush stroke compares with."""
        return (c in self.sel, self.place.get(c))

    def set_slot_item(self, slot, name):
        """Assign an item to a turtle slot (name=None frees the slot and forgets its blocks)."""
        if name is None:
            self.inv.pop(slot, None)
            for c in [c for c, s in self.place.items() if s == slot]:
                del self.place[c]
            return True
        if not 1 <= slot <= 16 or (slot not in self.inv and len(self.inv) >= MAX_SUPPLY_SLOTS):
            return False
        self.inv[slot] = name
        return True

    def resize(self, w, d, h):
        self.sel = {c for c in self.sel if c[0] <= w and c[1] <= h and c[2] <= d}
        self.place = {c: s for c, s in self.place.items() if c in self.sel}
        self.w, self.d, self.h = w, d, h
        self.tx, self.tz, self.ty = min(self.tx, w), min(self.tz, d), min(self.ty, h)
        self.sel.discard(self.turtle)
        self.place.pop(self.turtle, None)
        self.marks = {n: m for n, m in self.marks.items() if m[0] <= w and m[1] <= h and m[2] <= d}

    def set_mark(self, name, x, y, z, face="forward"):
        """Mark a cell of the base design as the start cell of a turtle job (name = the job's name)."""
        if not self.inside(x, y, z):
            raise ValueError("That cell is outside the grid.")
        if face not in MARK_FACES:
            raise ValueError("Facing must be forward, right, back or left.")
        name = clean_name(name)
        for n in [n for n, m in self.marks.items() if m[:3] == (x, y, z)]:
            del self.marks[n]                                # one station per cell
        self.marks[name] = (x, y, z, face)

    # ---- (de)serialisation: one 0/1 string per layer, z-major then x (matches the Lua side)
    def layer_strings(self):
        out = []
        for y in range(1, self.h + 1):
            out.append("".join("1" if (x, y, z) in self.sel else "0"
                               for z in range(1, self.d + 1) for x in range(1, self.w + 1)))
        return out

    def place_strings(self, cells=None):
        cells = self.place if cells is None else cells
        out = []
        for y in range(1, self.h + 1):
            out.append("".join(SLOT_CHARS[cells.get((x, y, z), 0)]
                               for z in range(1, self.d + 1) for x in range(1, self.w + 1)))
        return out

    def to_json(self):
        data = {"app": "carve-designer", "version": 1, "name": self.name,
                "w": self.w, "d": self.d, "h": self.h,
                "tx": self.tx, "ty": self.ty, "tz": self.tz,
                "chest": self.chest, "layers": self.layer_strings()}
        if self.inv:
            data["inv"] = {str(s): n for s, n in sorted(self.inv.items())}
        if self.place:
            data["place"] = self.place_strings()
        if self.pattern != "nearest":
            data["pattern"] = self.pattern
        if self.torch_mode != "first":
            data["torches"] = self.torch_mode
        if self.seal:
            data["seal"] = True
        if self.marks:
            data["marks"] = {n: list(m) for n, m in sorted(self.marks.items())}
        if self.skin != "crafty":
            data["skin"] = self.skin
        if self.skin == "custom":
            data["skinColors"] = [self.skin_body, self.skin_accent]
        return data

    @staticmethod
    def from_json(data):
        w, d, h = int(data["w"]), int(data["d"]), int(data["h"])
        if not (1 <= w <= MAXDIM and 1 <= d <= MAXDIM and 1 <= h <= MAXDIM):
            raise ValueError("size out of range")
        des = Design(w, d, h)
        des.tx, des.ty, des.tz = int(data["tx"]), int(data["ty"]), int(data["tz"])
        if not des.inside(*des.turtle):
            raise ValueError("turtle position outside the grid")
        des.chest = bool(data.get("chest", True))
        des.name = clean_name(str(data.get("name", "Carve job")))
        layers = data["layers"]
        if len(layers) != h:
            raise ValueError("layer count does not match height")
        for y, row in enumerate(layers, 1):
            if len(row) != w * d or set(row) - set("01"):
                raise ValueError("bad layer data")
            for i, ch in enumerate(row):
                if ch == "1":
                    des.sel.add((i % w + 1, y, i // w + 1))
        des.sel.discard(des.turtle)
        _read_inv(des, data.get("inv"))
        _read_place(des, data.get("place"))
        if data.get("pattern", "nearest") not in dict(PATTERNS) or data.get("torches", "first") not in dict(TORCH_MODES):
            raise ValueError("unknown pattern")
        des.pattern = data.get("pattern", "nearest")
        des.seal = data.get("seal") is True
        if data.get("skin") in dict(SKINS):
            des.skin = data["skin"]
        cols = data.get("skinColors")
        if (isinstance(cols, list) and len(cols) == 2
                and all(isinstance(c, str) and re.fullmatch(r"#[0-9a-fA-F]{6}", c) for c in cols)):
            des.skin_body, des.skin_accent = cols[0].lower(), cols[1].lower()
        des.torch_mode = data.get("torches", "first")
        marks = data.get("marks") or {}
        if not isinstance(marks, dict) or len(marks) > 40:
            raise ValueError("bad station marks")
        for n, m in marks.items():
            if not (isinstance(m, list) and len(m) == 4 and all(isinstance(v, int) and not isinstance(v, bool) for v in m[:3])
                    and m[3] in MARK_FACES):
                raise ValueError("bad station mark")
            des.set_mark(n, m[0], m[1], m[2], m[3])
        return des


def _read_inv(des, inv):
    if inv is None:
        return
    if not isinstance(inv, dict) or len(inv) > MAX_SUPPLY_SLOTS:
        raise ValueError("bad inventory data")
    for k, v in inv.items():
        slot, name = int(k), clean_item(str(v))
        if not 1 <= slot <= 16 or name is None:
            raise ValueError("bad inventory data")
        des.inv[slot] = name


def _read_place(des, layers):
    """layers: one string per layer (as place_strings) or None."""
    if not layers:
        return
    if len(layers) != des.h:
        raise ValueError("block layer count does not match height")
    for y, row in enumerate(layers, 1):
        if len(row) != des.w * des.d or set(row) - set(SLOT_CHARS):
            raise ValueError("bad block data")
        for i, ch in enumerate(row):
            slot = SLOT_CHARS.index(ch)
            c = (i % des.w + 1, y, i // des.w + 1)
            if slot and slot in des.inv and c in des.sel:
                des.place[c] = slot


def design_from_flat(name, w, d, h, turtle, chest, flat, place="", inv=None):
    """Rebuild a design from the turtle's own report (all layers joined into one 0/1 string)."""
    w, d, h = int(w), int(d), int(h)
    if not (1 <= w <= MAXDIM and 1 <= d <= MAXDIM and 1 <= h <= MAXDIM) or len(flat) != w * d * h:
        raise ValueError("bad design from turtle")
    des = Design(w, d, h)
    des.name, des.chest = clean_name(str(name)), bool(chest)
    des.tx, des.ty, des.tz = (int(v) for v in turtle)
    if not des.inside(*des.turtle):
        raise ValueError("turtle position outside the grid")
    for i, ch in enumerate(flat):
        if ch == "1":
            des.sel.add((i % w + 1, i // (w * d) + 1, (i % (w * d)) // w + 1))
    des.sel.discard(des.turtle)
    _read_inv(des, inv)
    if place:
        if len(place) != w * d * h or set(place) - set(SLOT_CHARS):
            raise ValueError("bad block data from turtle")
        _read_place(des, [place[y * w * d:(y + 1) * w * d] for y in range(h)])
    return des


def cell_from_index(i, w, d):
    """The turtle's 1-based cell index (as used in its Lua code) -> (x, y, z)."""
    i0 = i - 1
    return (i0 % w + 1, i0 // (w * d) + 1, (i0 % (w * d)) // w + 1)


def flood(sel, start):
    """Cells of `sel` reachable from `start` by face-adjacent steps (start included)."""
    seen = {start}
    stack = [start]
    while stack:
        x, y, z = stack.pop()
        for dx, dy, dz in DIRS:
            n = (x + dx, y + dy, z + dz)
            if n not in seen and n in sel:
                seen.add(n)
                stack.append(n)
    return seen


def build_run(design):
    """Mirror of the turtle's planner: returns (cells_to_mine_incl_start, total, skipped)."""
    start = design.turtle
    run = set(design.sel)
    run.add(start)
    cc = design.chest_cell
    if design.chest and cc is not None:
        run.discard(cc)                       # never dig out the chest
    reach = flood(run, start)
    skipped = len(run - reach)
    return reach, len(reach) - 1, skipped


def _is_torch(design, slot):
    return "torch" in design.inv.get(slot, "")


def _torch_valid(design, run, raw, c):
    """A torch is dropped straight down from the cell above it onto the floor, so it needs a dug cell
    above (to stand in, with nothing placed there) and something solid below that stays."""
    a = (c[0], c[1] + 1, c[2])
    if a not in run or a in design.place:
        return False
    b = (c[0], c[1] - 1, c[2])
    if design.chest and b == design.chest_cell:
        return False
    if b not in run:
        return True                               # the ground, or a block that is left alone
    s = raw.get(b)
    return s is not None and not any(wd in design.inv.get(s, "") for wd in NONSOLID_WORDS)


def _raw_place(design):
    run, _total, _skipped = build_run(design)
    start = design.turtle
    return run, {c: s for c, s in design.place.items() if c in run and c != start and s in design.inv}


def build_place(design):
    """What the turtle will really place: {cell: slot} for reachable cells (never the start or chest).
    Torches that have no dug cell above them or no solid floor under them are left out."""
    run, raw = _raw_place(design)
    return {c: s for c, s in raw.items() if not _is_torch(design, s) or _torch_valid(design, run, raw, c)}


def bad_torches(design):
    """Torch cells that can't be placed (nothing to stand in above them / no solid floor)."""
    run, raw = _raw_place(design)
    return sorted(c for c, s in raw.items() if _is_torch(design, s) and not _torch_valid(design, run, raw, c))


def supply_needs(design):
    """{slot: number of blocks the job places from it}"""
    need = {}
    for s in build_place(design).values():
        need[s] = need.get(s, 0) + 1
    return need


NONSOLID_WORDS = ("torch", "lantern", "ladder", "pane", "bars", "chain", "rod", "door", "sign")


def auto_torches(design, spacing, slot):
    """Mark floor cells on a grid for torches. Returns how many were added.

    A torch goes on the floor of the finished room - an open (dug, nothing placed) cell with
    something solid under it and a dug cell above it for the turtle to stand in - every `spacing`
    cells, centred in each square. If you fill the floor with blocks, torches sit on top of them.
    Cells that already have a block are left alone.
    """
    spacing = max(1, int(spacing))
    run, _total, _skipped = build_run(design)
    start = design.turtle

    def solid_below(c):
        b = (c[0], c[1] - 1, c[2])
        if b in design.place:
            item = design.inv.get(design.place[b], "")
            return not any(w in item for w in NONSOLID_WORDS)
        return b not in run

    added = 0
    for c in sorted(run):
        above = (c[0], c[1] + 1, c[2])
        if c == start or c in design.place or not solid_below(c) or above not in run or above in design.place:
            continue
        if (c[0] - 1) % spacing == spacing // 2 and (c[2] - 1) % spacing == spacing // 2:
            design.place[c] = slot
            added += 1
    return added


def clear_blocks(design, slot=None):
    """Forget placement for every cell (or only those using `slot`); the digging stays."""
    for c in [c for c, s in design.place.items() if slot is None or s == slot]:
        del design.place[c]


# ================================================================ generated programs
def normalize_live_url(url):
    """http://host:port  ->  cleaned, or '' when it isn't something the turtle can use."""
    url = (url or "").strip().rstrip("/")
    if re.fullmatch(r"http://[A-Za-z0-9._\-]+(:\d{1,5})?", url):
        return url
    return ""


def generate_lua(design, live_url=""):
    live_url = normalize_live_url(live_url)
    plan = [
        "-- Shape: %dx%dx%d (right x forward x up), turtle cell x=%d y=%d z=%d" % (
            design.w, design.d, design.h, design.tx, design.ty, design.tz),
        "local PLAN = {",
        '  name = "%s",' % clean_name(design.name),
        '  live = "%s",' % live_url,
        "  w = %d, d = %d, h = %d," % (design.w, design.d, design.h),
        "  tx = %d, ty = %d, tz = %d," % (design.tx, design.ty, design.tz),
        "  chest = %s," % ("true" if design.chest else "false"),
        '  pattern = "%s", torches = "%s",' % (design.pattern, design.torch_mode),
        '  seal = %s,' % ("true" if design.seal else "false"),
        "  layers = {",
    ]
    for y, row in enumerate(design.layer_strings(), 1):
        plan.append('    "%s",  -- layer %d' % (row, y))
    plan.append("  },")
    if design.inv:
        plan.append("  inv = { %s }," % ", ".join('[%d] = "%s"' % (s, n) for s, n in sorted(design.inv.items())))
    valid = build_place(design)
    if valid:
        plan.append("  place = {")
        for y, row in enumerate(design.place_strings(valid), 1):
            plan.append('    "%s",  -- layer %d' % (row, y))
        plan.append("  },")
    plan.append("}")
    return TURTLE_TEMPLATE.replace("--@@PLAN@@", "\n".join(plan), 1)


def check_repo_settings(repo, branch, folder):
    """Validate/clean the GitHub settings. Returns (repo, branch, folder)."""
    repo = (repo or "").strip().strip("/")
    if not re.fullmatch(r"[A-Za-z0-9_.\-]+/[A-Za-z0-9_.\-]+", repo):
        raise UploadError("Repository must look like  owner/name")
    branch = (branch or "").strip() or "main"
    if not re.fullmatch(r"[A-Za-z0-9_.\-/]+", branch) or ".." in branch:
        raise UploadError("That branch name has characters I can't use.")
    folder = (folder or "").strip().strip("/")
    if folder and (not re.fullmatch(r"[A-Za-z0-9_.\-/]+", folder) or ".." in folder):
        raise UploadError("Folder may only use letters, digits, _ - . and /")
    return repo, branch, folder


def repo_path(folder, rel):
    return (folder + "/" + rel) if folder else rel


def raw_base(repo, branch, folder):
    base = "https://raw.githubusercontent.com/%s/%s" % (repo, urllib.parse.quote(branch, safe="/"))
    return base + ("/" + urllib.parse.quote(folder, safe="/") if folder else "")


def generate_launcher(repo, branch, folder):
    repo, branch, folder = check_repo_settings(repo, branch, folder)
    return LAUNCHER_TEMPLATE.replace("@@BASE@@", json.dumps(raw_base(repo, branch, folder)), 1)


# ============================================================= saved designs & settings
def library_dir():
    return os.path.join(CONFIG_DIR, "designs")


def library_save(design):
    os.makedirs(library_dir(), exist_ok=True)
    slug = design.slug()
    tmp = os.path.join(library_dir(), slug + ".json.tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(design.to_json(), f)
    os.replace(tmp, os.path.join(library_dir(), slug + ".json"))
    return slug


def library_load(slug):
    with open(os.path.join(library_dir(), slugify(slug) + ".json"), "r", encoding="utf-8") as f:
        return Design.from_json(json.load(f))


def library_delete(slug):
    try:
        os.remove(os.path.join(library_dir(), slugify(slug) + ".json"))
    except OSError:
        pass


def library_list():
    """Saved designs on this computer, newest first: [dict(name, slug, size, blocks, mtime)]."""
    out = []
    try:
        names = os.listdir(library_dir())
    except OSError:
        return out
    for fn in names:
        if not fn.endswith(".json"):
            continue
        path = os.path.join(library_dir(), fn)
        try:
            with open(path, "r", encoding="utf-8") as f:
                des = Design.from_json(json.load(f))
            out.append({"name": des.name, "slug": fn[:-5], "size": (des.w, des.d, des.h),
                        "blocks": build_run(des)[1], "mtime": os.path.getmtime(path)})
        except Exception:
            continue
    out.sort(key=lambda e: -e["mtime"])
    return out


def unique_name(base, taken_slugs):
    base = clean_name(base)
    n, name = 1, base
    while slugify(name) in taken_slugs:
        n += 1
        name = "%s %d" % (base[:26], n)
    return name


def load_config():
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_config(cfg):
    try:
        os.makedirs(CONFIG_DIR, exist_ok=True)
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2)
        try:
            os.chmod(CONFIG_FILE, 0o600)      # may hold a token if the user opted in
        except OSError:
            pass
    except OSError:
        pass


def import_old_design():
    """Version 1 kept one 'last design' file; bring it into the list the first time."""
    if library_list():
        return
    try:
        with open(LAST_DESIGN_FILE, "r", encoding="utf-8") as f:
            library_save(Design.from_json(json.load(f)))
    except Exception:
        pass
