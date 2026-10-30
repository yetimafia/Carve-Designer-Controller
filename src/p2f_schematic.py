# Reads Minecraft schematics (.nbt / .schem) so a build can be imported as a design. Blocks that cannot be dug or placed are skipped (NBT_SKIP).
# ---------------------------------------------------------------------------- schematic import
NBT_SKIP = {"air", "cave_air", "void_air", "water", "lava", "bubble_column", "fire", "soul_fire", "light",
            "barrier", "structure_void", "structure_block", "jigsaw", "moving_piston", "piston_head"}
NBT_REMAP = {"wall_torch": "torch", "redstone_wall_torch": "redstone_torch", "soul_wall_torch": "soul_torch",
             "redstone_wire": "redstone", "tripwire": "string", "wheat": "wheat_seeds", "carrots": "carrot",
             "potatoes": "potato", "beetroots": "beetroot_seeds", "melon_stem": "melon_seeds",
             "pumpkin_stem": "pumpkin_seeds", "sweet_berry_bush": "sweet_berries", "cocoa": "cocoa_beans",
             "kelp_plant": "kelp", "tall_seagrass": "seagrass", "frosted_ice": "ice", "bamboo_sapling": "bamboo",
             "cave_vines": "glow_berries", "cave_vines_plant": "glow_berries", "tall_grass": "short_grass",
             "grass": "short_grass", "lava_cauldron": "cauldron", "water_cauldron": "cauldron"}


class SchematicError(Exception):
    pass


def read_nbt(raw):
    """Parse (optionally gzipped) NBT bytes into plain Python values: the root compound as a dict."""
    if raw[:2] == b"\x1f\x8b":
        raw = gzip.decompress(raw)
    pos = [0]

    def take(n):
        if pos[0] + n > len(raw):
            raise SchematicError("The file ends too early - is it damaged?")
        b = raw[pos[0]:pos[0] + n]
        pos[0] += n
        return b

    def string():
        return take(struct.unpack(">H", take(2))[0]).decode("utf-8", "replace")

    def payload(t):
        if t == 1:
            return struct.unpack(">b", take(1))[0]
        if t == 2:
            return struct.unpack(">h", take(2))[0]
        if t == 3:
            return struct.unpack(">i", take(4))[0]
        if t == 4:
            return struct.unpack(">q", take(8))[0]
        if t == 5:
            return struct.unpack(">f", take(4))[0]
        if t == 6:
            return struct.unpack(">d", take(8))[0]
        if t == 7:
            n = struct.unpack(">i", take(4))[0]
            return take(n)
        if t == 8:
            return string()
        if t == 9:
            et = take(1)[0]
            n = struct.unpack(">i", take(4))[0]
            if n > 20_000_000:
                raise SchematicError("That file is too big.")
            return [payload(et) for _ in range(n)]
        if t == 10:
            out = {}
            while True:
                tt = take(1)[0]
                if tt == 0:
                    return out
                key = string()
                out[key] = payload(tt)
        if t == 11:
            n = struct.unpack(">i", take(4))[0]
            return list(struct.unpack(">%di" % n, take(4 * n)))
        if t == 12:
            n = struct.unpack(">i", take(4))[0]
            return list(struct.unpack(">%dq" % n, take(8 * n)))
        raise SchematicError("Unknown data in the file (type %d)." % t)

    if take(1)[0] != 10:
        raise SchematicError("That is not a Minecraft structure file.")
    string()
    return payload(10)


def _clean_name(n):
    n = str(n).split("[", 1)[0]
    return n if ":" in n else "minecraft:" + n


def _litematic_blocks(root):
    regions = root.get("Regions")
    if not isinstance(regions, dict) or not regions:
        raise SchematicError("No regions found in that Litematica file.")
    out = {}
    for reg in regions.values():
        size = reg["Size"]
        pos = reg.get("Position", {"x": 0, "y": 0, "z": 0})
        sx, sy, sz = abs(size["x"]), abs(size["y"]), abs(size["z"])
        ox = pos["x"] + (size["x"] + 1 if size["x"] < 0 else 0)
        oy = pos["y"] + (size["y"] + 1 if size["y"] < 0 else 0)
        oz = pos["z"] + (size["z"] + 1 if size["z"] < 0 else 0)
        palette = [_clean_name(p.get("Name", "minecraft:air")) for p in reg["BlockStatePalette"]]
        bits = max(2, (len(palette) - 1).bit_length())
        longs = [v & 0xFFFFFFFFFFFFFFFF for v in reg["BlockStates"]]
        mask = (1 << bits) - 1
        i = 0
        for y in range(sy):
            for z in range(sz):
                for x in range(sx):
                    bp = i * bits
                    i += 1
                    li, off = bp >> 6, bp & 63
                    if li >= len(longs):
                        continue
                    v = longs[li] >> off
                    if off + bits > 64 and li + 1 < len(longs):
                        v |= longs[li + 1] << (64 - off)
                    idx = v & mask
                    if idx < len(palette):
                        out[(ox + x, oy + y, oz + z)] = palette[idx]
    return out


def _sponge_blocks(root):
    if "Schematic" in root and isinstance(root["Schematic"], dict):
        root = root["Schematic"]
    w, h, l = root["Width"] & 0xFFFF, root["Height"] & 0xFFFF, root["Length"] & 0xFFFF
    if "Blocks" in root:                                  # version 3
        pal, data = root["Blocks"]["Palette"], root["Blocks"]["Data"]
    else:
        pal, data = root["Palette"], root["BlockData"]
    names = {int(i): _clean_name(n) for n, i in pal.items()}
    vals, cur, shift = [], 0, 0
    for b in data:
        cur |= (b & 0x7F) << shift
        if b & 0x80:
            shift += 7
        else:
            vals.append(cur)
            cur, shift = 0, 0
    out = {}
    i = 0
    for y in range(h):
        for z in range(l):
            for x in range(w):
                if i < len(vals):
                    out[(x, y, z)] = names.get(vals[i], "minecraft:air")
                i += 1
    return out


def _structure_blocks(root):
    pal = [_clean_name(p.get("Name", "minecraft:air")) for p in root["palette"]]
    out = {}
    for b in root["blocks"]:
        x, y, z = b["pos"]
        out[(x, y, z)] = pal[b["state"]]
    return out


def load_schematic(path):
    """Read a .litematic / .schem / .nbt file: returns {(x, y, z): 'minecraft:name'} (0-based, air kept)."""
    try:
        with open(path, "rb") as fh:
            root = read_nbt(fh.read(60_000_000))
    except OSError as ex:
        raise SchematicError("Could not read that file: %s" % ex)
    try:
        if "Regions" in root:
            return _litematic_blocks(root)
        if "Palette" in root or "Schematic" in root or "Blocks" in root:
            return _sponge_blocks(root)
        if "palette" in root and "blocks" in root:
            return _structure_blocks(root)
    except (KeyError, TypeError, IndexError) as ex:
        raise SchematicError("That file is laid out in a way I don't understand (%s)." % ex)
    raise SchematicError("I can open .litematic, .schem and structure .nbt files - this isn't one of them.")


def _rgb(item):
    c = item_color(item)
    return int(c[1:3], 16), int(c[3:5], 16), int(c[5:7], 16)


def schematic_design(blocks, name="Imported build", margin=True):
    """Turn the blocks of a build into a design: every block gets dug and replaced by the same block, so
    it works in solid ground or open air. Only 8 kinds fit in the turtle: the rarer ones become
    the most similar colour of the 8 most common. Returns (design, report)."""
    counts = {}
    cells = {}
    for (x, y, z), n in blocks.items():
        short = n.split(":", 1)[-1]
        if short in NBT_SKIP:
            continue
        short = NBT_REMAP.get(short, short)
        item = "minecraft:" + short if n.startswith("minecraft:") else n
        if n.startswith("minecraft:"):
            item = "minecraft:" + short
        cells[(x, y, z)] = item
        counts[item] = counts.get(item, 0) + 1
    if not cells:
        raise SchematicError("That build has no blocks in it.")
    xs, ys, zs = [c[0] for c in cells], [c[1] for c in cells], [c[2] for c in cells]
    sx, sy, sz = max(xs) - min(xs) + 1, max(ys) - min(ys) + 1, max(zs) - min(zs) + 1
    pad = 1 if (margin and sz < MAXDIM) else 0
    if max(sx, sy, sz + pad) > MAXDIM:
        raise SchematicError("That build is %d x %d x %d. The biggest I can dig is %d in each direction - "
                             "trim it in Litematica/WorldEdit first." % (sx, sy, sz, MAXDIM))
    ranked = sorted(counts, key=lambda k: (-counts[k], k))
    chosen = ranked[:MAX_SUPPLY_SLOTS]
    mapping = {}
    for item in ranked:
        if item in chosen:
            mapping[item] = item
        else:
            r, g, b = _rgb(item)
            mapping[item] = min(chosen, key=lambda c: sum((u - v) ** 2 for u, v in zip(_rgb(c), (r, g, b))))
    des = Design(sx, sz + pad, sy)
    des.name = name
    for i, item in enumerate(chosen):
        des.inv[i + 1] = item
    slot_of = {item: i + 1 for i, item in enumerate(chosen)}
    placed = {}
    for (x, y, z), item in cells.items():
        placed[(x - min(xs) + 1, y - min(ys) + 1, z - min(zs) + 1 + pad)] = slot_of[mapping[item]]
    # where the turtle stands: in the spare row in front of the build, at a column that has a block next to it
    start = None
    if pad:
        for (x, y, z) in sorted(placed, key=lambda c: (c[1], abs(c[0] - (sx + 1) / 2.0), c[0])):
            if z == 2:
                start = (x, y, 1)
                break
    if start is not None:
        des.tx, des.ty, des.tz = start
    else:
        first = min(placed, key=lambda c: (c[2], c[1], abs(c[0] - (sx + 1) / 2.0), c[0]))
        des.tx, des.ty, des.tz = first
    for c, slot in placed.items():
        des.set_cell(c[0], c[1], c[2], True, slot=slot)
    skipped = sum(1 for c in placed if c == des.turtle)
    report = {"blocks": len(placed) - skipped, "kinds": len(counts), "mapped": len(counts) - len(chosen) if len(counts) > len(chosen) else 0,
              "size": (sx, sz, sy), "unreachable": build_run(des)[2], "items": [(i, counts[i]) for i in chosen]}
    return des, report
