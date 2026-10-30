# Importing the player's own textures (resource packs, the game jar, mods). They are read on the player's computer and kept in
# the settings folder; nothing is uploaded. Why: the player may want the real look, but we must not redistribute it.
# ============================================================ your own textures (resource packs, game jar, mods)
# Textures you import stay on your computer (in the settings folder); nothing is uploaded anywhere.
TEX = {"mode": "builtin", "tiles": {}, "sources": []}      # mode: builtin | imported


def texpack_file():
    return os.path.join(CONFIG_DIR, "textures.json.gz")


_TEX_NAME = re.compile(r"assets/([a-z0-9_.\-]+)/textures/(block|blocks|item|items)/([a-z0-9_.\-]+)\.png")
_SUFFIXES = ("", "_side", "_front", "_top")
_GREEN = {"leaves": (0.30, 0.55, 0.20), "grass": (0.36, 0.62, 0.24), "fern": (0.30, 0.55, 0.22),
          "vine": (0.30, 0.55, 0.22), "lily_pad": (0.18, 0.45, 0.20)}


def _pack_encode(rows):
    return "".join("------" if c is None else "%02x%02x%02x" % c for row in rows for c in row)


def _pack_decode(s):
    out = []
    for y in range(16):
        row = []
        for x in range(16):
            h = s[(y * 16 + x) * 6:(y * 16 + x) * 6 + 6]
            row.append(None if h == "------" else (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)))
        out.append(row)
    return out


def load_texpack():
    TEX["tiles"], TEX["sources"] = {}, []
    try:
        with gzip.open(texpack_file(), "rt", encoding="utf-8") as f:
            data = json.load(f)
        tiles = data.get("tiles", {})
        if isinstance(tiles, dict):
            TEX["tiles"] = {k: v for k, v in tiles.items() if isinstance(k, str) and isinstance(v, str) and len(v) == 1536}
            TEX["sources"] = [str(s) for s in data.get("sources", [])][:50]
    except Exception:
        pass


def save_texpack():
    try:
        os.makedirs(CONFIG_DIR, exist_ok=True)
        with gzip.open(texpack_file(), "wt", encoding="utf-8") as f:
            json.dump({"sources": TEX["sources"], "tiles": TEX["tiles"]}, f, separators=(",", ":"))
    except OSError:
        pass


def clear_texpack():
    TEX["tiles"], TEX["sources"], TEX["mode"] = {}, [], "builtin"
    try:
        os.remove(texpack_file())
    except OSError:
        pass


def pack_tile(name):
    """The imported texture for an item id (vanilla or modded), or None."""
    tiles = TEX["tiles"]
    if not tiles:
        return None
    ns, _, short = name.partition(":")
    for suf in _SUFFIXES:
        s = tiles.get("%s:%s%s" % (ns, short, suf))
        if s:
            return _pack_decode(s)
    return None


def display_tile(name):
    """What to draw for an item: your imported texture when that mode is on, else our simplified tile."""
    if TEX["mode"] == "imported":
        t = pack_tile(name)
        if t is not None:
            return t
    return item_tile(name)


def display_color(name):
    """Flat colour of an item: the average of what is drawn, else the measured / hash colour."""
    t = display_tile(name) if TEX["mode"] == "imported" and pack_tile(name) is not None else None
    if t is None:
        return item_color(name)
    px = [c for row in t for c in row if c]
    if not px:
        return item_color(name)
    return "#%02x%02x%02x" % tuple(sum(c[i] for c in px) // len(px) for i in range(3))


def _greenify(short, rows):
    for word, tint in _GREEN.items():
        if word in short:
            px = [c for row in rows for c in row if c]
            if px and max(max(c) - min(c) for c in px) < 30:         # grey texture the game would tint
                return [[None if c is None else tuple(min(255, int(tint[i] * 255 * (0.55 + sum(c) / 765.0))) for i in range(3))
                         for c in row] for row in rows]
    return rows


def import_texture_file(root, path, limit=8000):
    """Read every block/item texture from a resource pack (.zip), the game's version .jar, or a mod .jar.
    Returns how many textures were added. Raises ValueError for files that are not zip archives."""
    try:
        z = zipfile.ZipFile(path)
    except (zipfile.BadZipFile, OSError):
        raise ValueError("That isn't a resource pack or jar file (a zip archive).")
    found = {}
    with z:
        entries = []
        for info in z.infolist():
            m = _TEX_NAME.fullmatch(info.filename)
            if m and info.file_size < 3_000_000:
                entries.append((0 if m.group(2).startswith("block") else 1, m.group(1), m.group(3), info))
        entries.sort(key=lambda e: e[0])                    # item textures win over block ones of the same name
        for _kind, ns, short, info in entries[:limit]:
            try:
                img = tk.PhotoImage(master=root, data=base64.b64encode(z.read(info)).decode("ascii"))
            except Exception:
                continue
            w, h = img.width(), img.height()
            side = min(w, h)                                # tall strips are animations: use the first frame
            if side < 1:
                continue
            rows = []
            for ty in range(16):
                row = []
                for tx in range(16):
                    sx, sy = min(w - 1, int((tx + 0.5) * side / 16)), min(h - 1, int((ty + 0.5) * side / 16))
                    if img.transparency_get(sx, sy):
                        row.append(None)
                    else:
                        v = img.get(sx, sy)
                        if isinstance(v, str):
                            v = v.split()
                        row.append((int(v[0]), int(v[1]), int(v[2])))
                rows.append(row)
            if all(c is None for row in rows for c in row):
                continue
            found["%s:%s" % (ns, short)] = _pack_encode(_greenify(short, rows))
    if not found:
        raise ValueError("No textures found. A resource pack has  assets/minecraft/textures/block  inside it.")
    TEX["tiles"].update(found)
    label = os.path.basename(path)
    if label not in TEX["sources"]:
        TEX["sources"].append(label)
    TEX["mode"] = "imported"
    save_texpack()
    return len(found)


def pack_names():
    return sorted(k for k in TEX["tiles"] if not k.endswith(("_side", "_front", "_top")) or k.split(":")[0] != "minecraft")
