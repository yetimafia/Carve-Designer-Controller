# The shape generators (box, cylinder, sphere ...) and ready-made templates that fill the design grid.
# ---------------------------------------------------------------------------- shapes and templates
SHAPES = [
    ("box", "Box / room"),
    ("cylinder", "Cylinder (round shaft)"),
    ("sphere", "Sphere / ball cave"),
    ("dome", "Dome (half sphere)"),
    ("pyramid", "Pyramid"),
    ("stairs", "Staircase going up"),
]


def _solid_shape(kind, w, d, h):
    """All cells of the plain solid shape that fits the w x d x h box."""
    out = set()
    cx, cz = (w + 1) / 2.0, (d + 1) / 2.0
    rx, rz = w / 2.0, d / 2.0
    if kind == "box":
        return {(x, y, z) for y in range(1, h + 1) for z in range(1, d + 1) for x in range(1, w + 1)}
    if kind == "cylinder":
        for y in range(1, h + 1):
            for z in range(1, d + 1):
                for x in range(1, w + 1):
                    if ((x - cx) / rx) ** 2 + ((z - cz) / rz) ** 2 <= 1.0:
                        out.add((x, y, z))
        return out
    if kind in ("sphere", "dome"):
        ry = h / 2.0 if kind == "sphere" else float(h)
        cy = (h + 1) / 2.0 if kind == "sphere" else 0.5
        for y in range(1, h + 1):
            for z in range(1, d + 1):
                for x in range(1, w + 1):
                    if ((x - cx) / rx) ** 2 + ((z - cz) / rz) ** 2 + ((y - cy) / ry) ** 2 <= 1.0:
                        out.add((x, y, z))
        return out
    if kind == "pyramid":
        for y in range(1, h + 1):
            f = 1.0 - (y - 1) / float(h)
            hx, hz = rx * f, rz * f
            for z in range(1, d + 1):
                for x in range(1, w + 1):
                    if abs(x - cx) <= hx and abs(z - cz) <= hz - 0.01:
                        out.add((x, y, z))
        return out
    if kind == "stairs":
        lo, hi = max(1, int(cx - 1)), min(w, int(cx + 1.5))
        steps = min(h - 1, d)
        for k in range(steps):
            for x in range(lo, hi + 1):
                out.add((x, k + 1, k + 1))
                out.add((x, k + 2, k + 1))
        return out
    raise ValueError(kind)


def shape_cells(kind, w, d, h, hollow=False, caps=True):
    """Cells to dig for a shape. hollow = only the outer skin (walls); caps = floor and ceiling too."""
    solid = _solid_shape(kind, w, d, h)
    if not hollow or kind == "stairs":
        return solid
    if kind == "box":
        side = ((1, 0, 0), (-1, 0, 0), (0, 0, 1), (0, 0, -1))
        ends = ((0, 1, 0), (0, -1, 0))
    else:                          # curved skins need the diagonal neighbours too, or they fall apart
        side = tuple((a, 0, c) for a in (-1, 0, 1) for c in (-1, 0, 1) if (a, c) != (0, 0))
        ends = tuple((a, b, c) for a in (-1, 0, 1) for b in (-1, 1) for c in (-1, 0, 1))
    nbs = side + ends if (caps or kind in ("sphere", "dome", "pyramid")) else side
    shell = set()
    for (x, y, z) in solid:
        if any((x + a, y + b, z + c) not in solid for a, b, c in nbs):
            shell.add((x, y, z))
    return shell


def apply_cells(design, cells, replace=True, slot=None):
    """Put `cells` into the design and stand the turtle on the first one (so the shape is reachable)."""
    if replace:
        design.sel = set()
        design.place = {}
    if not cells:
        return 0
    start = min(cells, key=lambda c: (c[2], c[1], abs(c[0] - (design.w + 1) / 2.0), c[0]))
    design.tx, design.ty, design.tz = start
    for c in cells:
        design.set_cell(c[0], c[1], c[2], True, slot=slot)
    design.sel.discard(design.turtle)
    design.place.pop(design.turtle, None)
    return len(cells)


def _mineshaft(d):
    cells = set()
    for z in range(1, d.d + 1):
        for y in range(1, 4):
            for x in range(3, 6):
                cells.add((x, y, z))
    for x in range(1, d.w + 1):                       # a cross tunnel half way
        for y in range(1, 4):
            for z in range(d.d // 2, d.d // 2 + 3):
                cells.add((x, y, z))
    return cells


TEMPLATES = [
    ("storage", "Storage room", "A roomy 11 x 9 x 4 hall for chests.", (11, 9, 4),
     lambda d: shape_cells("box", d.w, d.d, d.h)),
    ("mineshaft", "Mineshaft with a cross tunnel", "3 wide, 3 tall tunnel with a side tunnel.", (9, 24, 3),
     _mineshaft),
    ("tower", "Round tower shaft", "A 9 wide round shaft, 24 high.", (9, 9, 24),
     lambda d: shape_cells("cylinder", d.w, d.d, d.h)),
    ("stairs", "Staircase up", "A 3 wide staircase climbing 12 blocks.", (5, 13, 13),
     lambda d: shape_cells("stairs", d.w, d.d, d.h)),
    ("cave", "Round cave", "A 13 wide sphere to dig out.", (13, 13, 13),
     lambda d: shape_cells("sphere", d.w, d.d, d.h)),
    ("pyramid", "Pyramid chamber", "A 15 wide solid pyramid, 8 high.", (15, 15, 8),
     lambda d: shape_cells("pyramid", d.w, d.d, d.h)),
]


def template_design(key):
    for k, title, _blurb, (w, dd, h), fn in TEMPLATES:
        if k == key:
            design = Design(w, dd, h)
            design.name = title
            apply_cells(design, fn(design))
            return design
    raise KeyError(key)
