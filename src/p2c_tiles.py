# Our own 16x16 item pictures, drawn in code from a few measured colours per item, so the program never ships Mojang's pixels.
# Why: we wanted recognisable icons (Designer, Storage tab, Foreman tab) without bundling copyrighted textures.
# History: simple coloured shapes in the early versions; v7.7 added hand-drawn pictures for ingots, gems, dust, coal, tools, furnace,
# crafting table, hopper, glass, chest and for the ComputerCraft machines (see _special and _cc_tile).
# ============================================================ our own simplified item pictures
# Every vanilla item gets a 16x16 tile drawn here from four measured colours (average, dark, light, accent),
# so it looks like the real thing at a glance but contains none of Mojang's pixels.
import random as _random
import zlib as _zlib

_STATS = {}
EXTRA_STATS = {                      # items the game draws from a 3D model: colours picked by hand
    "chest": ("b", (160, 104, 45), (107, 68, 22), (197, 138, 69), (207, 207, 207)),
    "trapped_chest": ("b", (150, 98, 44), (101, 64, 22), (190, 132, 66), (186, 60, 50)),
    "ender_chest": ("b", (30, 60, 66), (14, 30, 36), (60, 120, 112), (96, 220, 180)),
    "torch": ("b", (139, 90, 43), (96, 60, 26), (255, 213, 74), (255, 213, 74)),
}


def icon_stats(name):
    """(kind, base, dark, light, accent) for a vanilla item id, or None for anything else (mods)."""
    if not _STATS:
        for part in ICON_DATA.split(";"):
            n, _, v = part.partition("=")
            k, rest = v[0], v[1:]
            cols = [tuple(int(c[i:i + 2], 16) for i in (0, 2, 4)) for c in rest.split(",")]
            _STATS[n] = (k, cols[0], cols[1], cols[2], cols[3])
    if not name.startswith("minecraft:"):
        return None
    short = name[10:]
    return _STATS.get(short) or EXTRA_STATS.get(short)


def icon_names():
    icon_stats("minecraft:stone")
    return sorted("minecraft:" + n for n in set(_STATS) | set(EXTRA_STATS))


def _mix(a, b, t):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


def _style(short, kind):
    if short.endswith("torch"):
        return "torch"
    if short == "chest" or short in ("trapped_chest", "ender_chest"):
        return "chest"
    if short.endswith("planks"):
        return "planks"
    if short.endswith("bricks") or short == "bricks" or short.endswith("_brick"):
        return "bricks"
    if short.endswith("_log") or short.endswith("_wood") or short.endswith("_stem") or short.endswith("_hyphae"):
        return "log"
    if "glass" in short and "bottle" not in short and "pane" not in short:
        return "glass"
    if "pane" in short:
        return "bars"
    if short.endswith("_ore") or short == "ancient_debris":
        return "ore"
    if short == "ladder":
        return "ladder"
    if short.endswith("_bars") or short == "iron_bars" or short == "chain":
        return "bars"
    if short.endswith("lantern") and short != "sea_lantern":
        return "lantern"
    if "leaves" in short:
        return "leaves"
    if kind == "i":
        return "gem"
    return "noise"


# ---- hand-drawn pictures for the things the colony is built from (ingots, gems, tools, ComputerCraft machines ...) ----
def _blank():
    return [[None] * 16 for _ in range(16)]


def _rect(g, x0, y0, x1, y1, c):
    for y in range(max(0, y0), min(15, y1) + 1):
        for x in range(max(0, x0), min(15, x1) + 1):
            g[y][x] = c


def _outline(g, amount=0.5):
    """Darken the outermost pixels so a shape stands out from the dark slot background."""
    edge = []
    for y in range(16):
        for x in range(16):
            if g[y][x] is None:
                continue
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                nx, ny = x + dx, y + dy
                if not (0 <= nx < 16 and 0 <= ny < 16) or g[ny][nx] is None:
                    edge.append((x, y))
                    break
    for x, y in edge:
        g[y][x] = _mix(g[y][x], (0, 0, 0), amount)
    return g


def _line(g, x0, y0, x1, y1, c, thick=1):
    n = max(abs(x1 - x0), abs(y1 - y0), 1)
    for i in range(n + 1):
        x = round(x0 + (x1 - x0) * i / n)
        y = round(y0 + (y1 - y0) * i / n)
        for dx in range(thick):
            for dy in range(thick):
                if 0 <= x + dx < 16 and 0 <= y + dy < 16:
                    g[y + dy][x + dx] = c


_TOOL = {"diamond": (77, 236, 222), "iron": (216, 216, 216), "golden": (250, 220, 60), "stone": (140, 140, 140),
         "wooden": (150, 110, 60), "netherite": (70, 60, 66)}
_INGOT = {"iron_ingot": (216, 216, 216), "gold_ingot": (250, 214, 56), "copper_ingot": (210, 120, 80), "netherite_ingot": (74, 62, 68),
          "brick": (170, 80, 60), "nether_brick": (70, 30, 36)}
_GEM = {"diamond": (80, 232, 220), "emerald": (40, 200, 90), "lapis_lazuli": (40, 70, 190), "quartz": (235, 230, 220),
        "amethyst_shard": (170, 110, 220), "echo_shard": (30, 90, 110)}
_DUST = {"redstone": (200, 20, 20), "glowstone_dust": (240, 200, 80), "gunpowder": (90, 90, 90), "sugar": (245, 245, 245),
         "bone_meal": (240, 240, 230), "blaze_powder": (250, 170, 30)}
_LUMP = {"coal": (40, 40, 44), "charcoal": (62, 50, 44), "raw_iron": (210, 160, 130), "raw_gold": (240, 200, 60), "raw_copper": (190, 110, 70)}


# v7.7: hand-drawn pictures. Each branch draws shapes with _rect/_line, then _outline darkens the edge so it stands out on the dark slot background.
def _special(name):
    ns, _, short = name.partition(":")
    if ns == "computercraft":
        return _cc_tile(short)
    if ns != "minecraft":
        return None
    g = _blank()
    rng = _random.Random(_zlib.crc32(name.encode()))
    if short in _INGOT:                                   # a bar seen from slightly above
        b = _INGOT[short]
        lt, dk = _mix(b, (255, 255, 255), 0.45), _mix(b, (0, 0, 0), 0.4)
        for y, x0 in ((5, 5), (6, 4), (7, 3)):
            _rect(g, x0, y, x0 + 9, y, lt)
        _rect(g, 3, 8, 12, 12, b)
        _rect(g, 3, 12, 12, 12, dk)
        _rect(g, 13, 5, 13, 9, dk)
        _rect(g, 12, 8, 12, 12, _mix(b, dk, 0.5))
        return _outline(g)
    if short in _GEM:                                     # a cut stone: crown on top, point below
        b = _GEM[short]
        lt, dk = _mix(b, (255, 255, 255), 0.55), _mix(b, (0, 0, 0), 0.35)
        for y in range(2, 14):
            half = 3 + (y - 2) * 0.8 if y < 7 else max(0, 8.2 - (y - 7) * 1.5)
            for x in range(16):
                if abs(x - 7.5) <= half:
                    g[y][x] = b if x >= 8 else lt
        for x in range(16):
            if g[7][x] is not None:
                g[7][x] = dk
        for y in range(8, 13):
            if g[y][8] is not None:
                g[y][8] = dk
        g[4][6] = g[3][7] = (255, 255, 255)
        return _outline(g)
    if short in _DUST:                                    # a little heap of powder
        b = _DUST[short]
        for y in range(6, 14):
            half = 1 + (y - 6) * 0.85
            for x in range(16):
                if abs(x - 7.5) <= half:
                    g[y][x] = _mix(b, (255, 255, 255) if rng.random() < 0.3 else (0, 0, 0), 0.25 if rng.random() < 0.7 else 0.0)
        return _outline(g, 0.4)
    if short in _LUMP or short.startswith("raw_"):       # a rough lump
        b = _LUMP.get(short, (150, 150, 150))
        for y in range(16):
            for x in range(16):
                d = ((x - 7.5) ** 2 + (y - 8.5) ** 2) ** 0.5
                if d < 5.2 + rng.random() * 1.4:
                    g[y][x] = _mix(b, (255, 255, 255), 0.32) if (x + y) % 5 == 0 and x < 8 else (_mix(b, (0, 0, 0), 0.25) if x > 9 and y > 9 else b)
        return _outline(g, 0.55)
    if short == "stick":
        _line(g, 3, 13, 12, 4, (150, 106, 54), 2)
        _line(g, 4, 13, 13, 4, (96, 64, 28))
        return _outline(g)
    if short == "paper":
        _rect(g, 3, 2, 12, 13, (240, 240, 235))
        for y in (5, 7, 9, 11):
            _rect(g, 5, y, 10, y, (150, 150, 150))
        _rect(g, 11, 2, 12, 3, (190, 190, 185))
        return _outline(g, 0.45)
    if short == "sugar_cane":
        for x, top in ((3, 4), (7, 1), (11, 3)):
            for y in range(top, 15):
                g[y][x] = (136, 200, 90) if (y - top) % 5 else (86, 150, 52)
                g[y][x + 1] = (96, 160, 60)
        return _outline(g, 0.4)
    if short.endswith("sapling") or short == "bamboo":
        _rect(g, 7, 8, 8, 14, (120, 84, 40))
        for cx, cy in ((4, 6), (10, 6), (7, 3), (7, 7)):
            _rect(g, cx - 2, cy - 2, cx + 2, cy + 1, (70, 150, 50))
            _rect(g, cx - 1, cy - 1, cx + 1, cy, (110, 190, 70))
        return _outline(g, 0.45)
    if short.endswith("_pickaxe"):
        mat = _TOOL.get(short[:-8], (180, 180, 180))
        _line(g, 3, 14, 11, 6, (140, 98, 48), 2)
        hd, hl = _mix(mat, (0, 0, 0), 0.3), _mix(mat, (255, 255, 255), 0.4)
        for (x, y) in ((4, 5), (5, 3), (7, 2), (9, 2), (11, 3), (12, 5), (13, 7)):
            _rect(g, x, y, x + 1, y + 1, mat)
        for (x, y) in ((5, 4), (8, 3), (10, 3), (12, 6)):
            g[y][x] = hl
        g[7][13] = g[8][13] = hd
        return _outline(g)
    if short == "furnace" or short == "blast_furnace":
        for y in range(16):
            for x in range(16):
                g[y][x] = _mix((130, 130, 130), (80, 80, 80) if rng.random() < 0.4 else (170, 170, 170), 0.5)
        _rect(g, 4, 7, 11, 13, (36, 36, 38))
        _rect(g, 5, 11, 10, 13, (230, 120, 30))
        _rect(g, 6, 12, 9, 13, (255, 210, 80))
        _rect(g, 0, 0, 15, 0, (170, 170, 170))
        return _outline(g, 0.4)
    if short == "crafting_table":
        for y in range(16):
            for x in range(16):
                g[y][x] = (150, 106, 56) if (x // 2 + y // 3) % 2 else (136, 94, 48)
        _rect(g, 0, 0, 15, 1, (96, 62, 30))
        _rect(g, 2, 3, 13, 8, (190, 150, 90))
        for k in (6, 9):
            _rect(g, k, 3, k, 8, (96, 62, 30))
        for k in (5, 7):
            _rect(g, 2, k, 13, k, (96, 62, 30))
        _rect(g, 3, 10, 5, 14, (110, 110, 110))
        _rect(g, 9, 11, 13, 13, (190, 190, 190))
        return _outline(g, 0.4)
    if short == "hopper":
        _rect(g, 1, 2, 14, 4, (70, 70, 74))
        _rect(g, 2, 3, 13, 3, (36, 36, 40))
        _rect(g, 2, 5, 13, 7, (96, 96, 100))
        _rect(g, 4, 8, 11, 9, (80, 80, 84))
        _rect(g, 6, 10, 9, 14, (70, 70, 74))
        _rect(g, 7, 11, 8, 14, (36, 36, 40))
        return _outline(g, 0.45)
    if short == "cobblestone":
        for y in range(16):
            for x in range(16):
                g[y][x] = (125, 125, 125)
        for by in range(0, 16, 5):
            off = rng.randrange(0, 5)
            for bx in range(-off, 16, 6):
                tone = _mix((125, 125, 125), (170, 170, 170) if rng.random() < 0.5 else (90, 90, 90), 0.4)
                _rect(g, bx + 1, by + 1, bx + 4, by + 3, tone)
        for y in range(16):
            for x in range(16):
                if g[y][x] == (125, 125, 125):
                    g[y][x] = (70, 70, 70)
                elif rng.random() < 0.3:
                    g[y][x] = _mix(g[y][x], (255, 255, 255) if rng.random() < 0.5 else (0, 0, 0), 0.12)
        return g
    if short == "stone":
        for y in range(16):
            for x in range(16):
                g[y][x] = _mix((125, 125, 125), (150, 150, 150) if rng.random() < 0.5 else (104, 104, 104), 0.5)
        return g
    if short in ("glass_pane", "glass"):                  # panes: a thin frame with a cross
        for y in range(16):
            for x in range(16):
                edge = x in (0, 15) or y in (0, 15)
                g[y][x] = (225, 245, 250) if edge else (170, 210, 225) if short == "glass_pane" else (190, 225, 235)
        if short == "glass_pane":
            _rect(g, 7, 0, 8, 15, (225, 245, 250))
            _rect(g, 0, 7, 15, 8, (225, 245, 250))
        for k in range(3, 6):
            g[k][k] = (255, 255, 255)
        return g
    if short == "chest":
        _rect(g, 1, 3, 14, 14, (160, 104, 45))
        _rect(g, 1, 3, 14, 7, (178, 122, 58))
        _rect(g, 1, 7, 14, 7, (96, 60, 22))
        _rect(g, 1, 11, 14, 11, (140, 90, 38))
        _rect(g, 7, 6, 8, 9, (225, 225, 225))
        return _outline(g, 0.45)
    return None


def _cc_tile(short):
    """ComputerCraft machines: grey casings, each with its own face."""
    g = _blank()
    case, rim, dark = (176, 176, 176), (210, 210, 210), (88, 88, 92)
    if short in ("computer_normal", "computer_advanced", "computer_command", "turtle_normal", "turtle_advanced"):
        gold = short.endswith("advanced")
        body = (230, 190, 60) if gold else case
        _rect(g, 1, 1, 14, 14, body)
        _rect(g, 1, 1, 14, 1, _mix(body, (255, 255, 255), 0.4))
        _rect(g, 1, 14, 14, 14, _mix(body, (0, 0, 0), 0.35))
        if short.startswith("computer"):                  # a screen with a prompt
            _rect(g, 3, 3, 12, 9, (20, 24, 40))
            _rect(g, 4, 5, 5, 5, (110, 255, 140)); _rect(g, 5, 6, 5, 6, (110, 255, 140)); _rect(g, 4, 7, 5, 7, (110, 255, 140))
            _rect(g, 7, 7, 9, 7, (110, 255, 140))
            _rect(g, 4, 11, 11, 12, _mix(body, (0, 0, 0), 0.2))
        else:                                             # a turtle: a face and a green shell
            _rect(g, 3, 3, 12, 8, (36, 40, 52))
            _rect(g, 4, 4, 5, 6, (255, 255, 255)); _rect(g, 10, 4, 11, 6, (255, 255, 255))
            _rect(g, 5, 5, 5, 6, (0, 0, 0)); _rect(g, 11, 5, 11, 6, (0, 0, 0))
            _rect(g, 6, 8, 9, 8, (255, 255, 255))
            _rect(g, 3, 10, 12, 13, (60, 160, 80))
            _rect(g, 4, 11, 6, 12, (90, 200, 110)); _rect(g, 9, 11, 11, 12, (90, 200, 110))
        return _outline(g, 0.5)
    if short == "disk_drive":
        _rect(g, 1, 2, 14, 13, case)
        _rect(g, 1, 2, 14, 2, rim)
        _rect(g, 3, 5, 12, 7, (30, 30, 34))                  # the slot
        _rect(g, 4, 6, 11, 6, (70, 70, 76))
        _rect(g, 11, 10, 12, 11, (80, 220, 90))              # the light
        _rect(g, 3, 10, 6, 11, dark)
        return _outline(g, 0.5)
    if short == "disk":                                   # a floppy disk
        _rect(g, 2, 1, 13, 14, (60, 110, 200))
        _rect(g, 5, 1, 10, 5, (200, 200, 205))               # the metal shutter
        _rect(g, 8, 2, 9, 4, (90, 90, 96))
        _rect(g, 4, 8, 11, 13, (240, 240, 235))              # the label
        for y in (10, 12):
            _rect(g, 5, y, 10, y, (150, 150, 150))
        return _outline(g, 0.5)
    rng = _random.Random(_zlib.crc32(short.encode()))
    _rect(g, 1, 1, 14, 14, case)                          # any other ComputerCraft part: a grey casing with its own coloured mark
    _rect(g, 1, 1, 14, 1, rim)
    mark = tuple(60 + rng.randrange(170) for _ in range(3))
    _rect(g, 5, 5, 10, 10, mark)
    _rect(g, 6, 6, 9, 9, _mix(mark, (255, 255, 255), 0.35))
    return _outline(g, 0.5)


def item_tile(name):
    """16 rows of 16 (r, g, b) tuples (None = see-through) for a vanilla item, or None for modded ones."""
    sp = _special(name)
    if sp is not None:
        return sp
    st = icon_stats(name)
    if st is None:
        return None
    kind, base, dark, light, acc = st
    short = name[10:]
    rng = _random.Random(_zlib.crc32(name.encode()))
    style = _style(short, kind)
    g = [[base] * 16 for _ in range(16)]

    def speckle(x0, y0, x1, y1, lo=0.17, hi=0.83, cell=2):
        for cy in range(y0, y1, cell):
            for cx in range(x0, x1, cell):
                r = rng.random()
                c = dark if r < lo else (light if r > hi else None)
                if c is None:
                    continue
                for yy in range(cy, min(cy + cell, y1)):
                    for xx in range(cx, min(cx + cell, x1)):
                        g[yy][xx] = _mix(base, c, 0.75)
        for yy in range(y0, y1):                       # a little per-pixel jitter
            for xx in range(x0, x1):
                if rng.random() < 0.12:
                    g[yy][xx] = _mix(g[yy][xx], dark if rng.random() < 0.5 else light, 0.35)

    if style == "noise":
        speckle(0, 0, 16, 16)
    elif style == "ore":
        speckle(0, 0, 16, 16, 0.2, 0.8, 2)
        for _ in range(6):
            sx, sy = rng.randrange(1, 14), rng.randrange(1, 14)
            for dx, dy in ((0, 0), (1, 0), (0, 1)):
                g[sy + dy][sx + dx] = acc
    elif style == "planks":
        for row in range(4):
            y0 = row * 4
            tone = _mix(base, light if row % 2 else dark, 0.18)
            for y in range(y0, y0 + 4):
                for x in range(16):
                    g[y][x] = tone
            for x in range(16):
                g[y0 + 3][x] = _mix(base, dark, 0.7)
            seam = (row * 5 + 3) % 14 + 1
            for y in range(y0, y0 + 3):
                g[y][seam] = _mix(base, dark, 0.55)
            for _ in range(3):
                g[y0 + rng.randrange(3)][rng.randrange(16)] = _mix(tone, dark, 0.3)
    elif style == "bricks":
        mortar = dark if ("stone" in short or "deepslate" in short or "nether" in short) else _mix(light, (215, 210, 200), 0.65)
        for y in range(16):
            for x in range(16):
                g[y][x] = base
        speckle(0, 0, 16, 16, 0.12, 0.88, 2)
        for y in range(16):
            for x in range(16):
                if y % 4 == 3:
                    g[y][x] = mortar
                else:
                    off = 4 if (y // 4) % 2 else 0
                    if (x + off) % 8 == 7:
                        g[y][x] = mortar
    elif style == "log":
        x = 0
        while x < 16:
            w = rng.choice((1, 2, 2, 3))
            c = rng.choice((dark, base, base, light))
            for xx in range(x, min(16, x + w)):
                for y in range(16):
                    g[y][xx] = _mix(base, c, 0.55)
            x += w
        for _ in range(10):
            g[rng.randrange(16)][rng.randrange(16)] = dark
    elif style == "glass":
        inner = _mix(base, (22, 28, 34), 0.55)
        for y in range(16):
            for x in range(16):
                edge = x in (0, 15) or y in (0, 15)
                g[y][x] = _mix(light, (255, 255, 255), 0.3) if edge else inner
        for k in range(3, 8):
            g[k][k] = (255, 255, 255)
        g[10][4] = g[4][10] = _mix(light, (255, 255, 255), 0.6)
    elif style == "chest":
        for y in range(16):
            for x in range(16):
                g[y][x] = _mix(base, light if y % 5 == 0 else dark, 0.22)
        for i in range(16):
            for (yy, xx) in ((0, i), (15, i), (i, 0), (i, 15)):
                g[yy][xx] = dark
            g[6][i] = dark
        for yy in (6, 7, 8):
            for xx in (7, 8):
                g[yy][xx] = acc
    elif style == "ladder":
        g = [[None] * 16 for _ in range(16)]
        for y in range(16):
            for x in (2, 3, 12, 13):
                g[y][x] = _mix(base, dark, 0.35)
        for y in (2, 3, 7, 8, 12, 13):
            for x in range(4, 12):
                g[y][x] = base
    elif style == "bars":
        g = [[None] * 16 for _ in range(16)]
        for y in range(16):
            for x in (5, 10):
                g[y][x] = light
                g[y][x + 1 if x + 1 < 16 else x] = _mix(base, dark, 0.4)
        for x in range(16):
            for y in (2, 13):
                g[y][x] = _mix(base, dark, 0.3)
    elif style == "lantern":
        g = [[None] * 16 for _ in range(16)]
        for y in range(3, 14):
            for x in range(4, 12):
                g[y][x] = acc if 5 <= y <= 11 and 5 <= x <= 10 else dark
        for x in range(6, 10):
            g[2][x] = dark
            g[1][x] = dark
        g[0][7] = g[0][8] = dark
    elif style == "torch":
        g = [[None] * 16 for _ in range(16)]
        for y in range(6, 16):
            g[y][7] = base
            g[y][8] = _mix(base, dark, 0.5)
        for (x, y) in ((7, 3), (8, 3), (7, 4), (8, 4), (6, 4), (9, 4), (7, 5), (8, 5), (6, 5), (9, 5)):
            g[y][x] = acc
        g[2][7] = g[2][8] = _mix(acc, (255, 255, 255), 0.6)
        g[3][7] = g[3][8] = _mix(acc, (255, 255, 255), 0.35)
    elif style == "leaves":
        speckle(0, 0, 16, 16, 0.3, 0.7, 2)
        for _ in range(14):
            g[rng.randrange(16)][rng.randrange(16)] = None
    else:                                                # gem: an item that isn't a block
        g = [[None] * 16 for _ in range(16)]
        for y in range(16):
            for x in range(16):
                d = ((x - 7.5) ** 2 + (y - 7.5) ** 2) ** 0.5
                if d <= 6.2:
                    shade = (x + y - 15) / 18.0
                    c = _mix(base, light if shade < 0 else dark, min(0.6, abs(shade)))
                    g[y][x] = dark if d > 5.3 else c
        g[4][5] = g[4][6] = g[5][5] = _mix(light, (255, 255, 255), 0.6)
        if acc != base:
            g[8][8] = g[8][9] = g[9][8] = acc
    return g


def tile_hex(name):
    """The tile as 16 rows of 16 'rrggbb' strings ('-' = see-through), for the 3D page; None for modded items."""
    t = display_tile(name)
    if t is None:
        return None
    return [["-" if c is None else "%02x%02x%02x" % c for c in row] for row in t]
