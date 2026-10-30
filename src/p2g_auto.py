# Automation jobs: settings, validation and defaults for the ready-made turtle programs (tree farm, smelter, crafter, miner, scout,
# hauler, storage keeper, foreman), plus the colony helpers (shopping list, layout).
# Versions: the shopping list (colony_materials) follows the Foreman's recipes - 7.4 added the hopper (5 iron + a chest), 7.5 added spare redstone;
# colony_layout leaves 10 blocks between jobs since 7.8.
# ---------------------------------------------------------------------------- automation jobs
# Tree farm, auto smelter and auto crafter are ready-made turtle programs with a few settings.
SAPLINGS = [("minecraft:oak_sapling", "Oak"), ("minecraft:spruce_sapling", "Spruce"), ("minecraft:birch_sapling", "Birch"),
            ("minecraft:acacia_sapling", "Acacia"), ("minecraft:cherry_sapling", "Cherry"),
            ("minecraft:mangrove_propagule", "Mangrove"), ("any", "Any sapling it finds")]
AUTO_KINDS = [("treefarm", "Tree farm"), ("smelter", "Auto smelter"), ("crafter", "Auto crafter"),
              ("hauler", "Hauler (carries items between jobs)"), ("keeper", "Storage keeper (chest warehouse)"), ("miner", "Miner (finds resources)"), ("scout", "Scout (maps the world)"),
              ("agent", "Agent (starts jobs on demand)"), ("foreman", "Foreman (sets up the other turtles)")]
MINER_RESOURCES = [("coal", "Coal"), ("iron", "Iron"), ("copper", "Copper"), ("gold", "Gold"), ("redstone", "Redstone"),
                   ("lapis", "Lapis"), ("diamond", "Diamond"), ("emerald", "Emerald")]

TREE_DEFAULT = {"kind": "treefarm", "name": "Tree farm", "cols": 3, "rows": 3, "spacing": 4,
                "sapling": "minecraft:oak_sapling", "bonemeal": False, "wait": 600, "cycles": 0, "chest": True}
SMELTER_DEFAULT = {"kind": "smelter", "name": "Auto smelter", "furnaces": 4, "fuel": "minecraft:coal", "once": False}
HAULER_DEFAULT = {"kind": "hauler", "name": "Hauler", "legs": [{"from": "", "to": "", "item": ""}], "wait": 20, "cycles": 0}
KEEPER_DEFAULT = {"kind": "keeper", "name": "Storage keeper", "length": 8, "wait": 10, "rescan": 1800}
FOREMAN_DEFAULT = {"kind": "foreman", "name": "Foreman", "jobs": [], "dispatch": True, "build": True, "agent_url": "", "launcher_url": ""}
KIT_TAGS = ("chest", "furnace", "sapling", "coal", "bonemeal")
MINER_DEFAULT = {"kind": "miner", "name": "Miner", "depth": 20, "reach": 30, "rib": 12,
                "want": [k for k, _l in MINER_RESOURCES]}
SCOUT_DEFAULT = {"kind": "scout", "name": "Scout", "radius": 24, "up": 8, "down": 4}
AGENT_DEFAULT = {"kind": "agent", "name": "Agent"}
CRAFTER_DEFAULT = {"kind": "crafter", "name": "Auto crafter", "grid": [None] * 9, "out": "", "total": 0, "once": False}


def auto_default(kind):
    base = {"treefarm": TREE_DEFAULT, "smelter": SMELTER_DEFAULT, "crafter": CRAFTER_DEFAULT,
            "scout": SCOUT_DEFAULT, "agent": AGENT_DEFAULT, "miner": MINER_DEFAULT, "hauler": HAULER_DEFAULT, "keeper": KEEPER_DEFAULT, "foreman": FOREMAN_DEFAULT}[kind]
    out = dict(base)
    if kind == "crafter":
        out["grid"] = [None] * 9
    if kind == "hauler":
        out["legs"] = [dict(l) for l in base["legs"]]
    if kind == "foreman":
        out["jobs"] = []
    return out


def _int(v, lo, hi, what):
    try:
        n = int(v)
    except (TypeError, ValueError):
        raise ValueError("%s must be a whole number." % what)
    if not lo <= n <= hi:
        raise ValueError("%s must be between %d and %d." % (what, lo, hi))
    return n


def clean_auto(p):
    """Validate / normalise one automation job (a dict). Raises ValueError with a friendly message."""
    kind = p.get("kind")
    if kind not in dict(AUTO_KINDS):
        raise ValueError("Unknown job type.")
    out = {"kind": kind, "name": clean_name(p.get("name") or dict(AUTO_KINDS)[kind])}
    label = str(p.get("label") or "").strip()
    if label:                                    # the computer label the turtle gives itself on its first start (if it has none)
        if not re.fullmatch(r"[A-Za-z0-9 _.\-]{1,30}", label):
            raise ValueError("The turtle's name may use letters, numbers, spaces and _ . - (up to 30).")
        out["label"] = label
    if kind == "treefarm":
        out["cols"] = _int(p.get("cols", 3), 1, 12, "Trees per row")
        out["rows"] = _int(p.get("rows", 3), 1, 12, "Rows")
        out["spacing"] = _int(p.get("spacing", 4), 3, 8, "Spacing")
        sap = p.get("sapling", "minecraft:oak_sapling")
        if sap not in dict(SAPLINGS) and not clean_item(sap):
            raise ValueError("Pick a sapling.")
        out["sapling"] = sap
        out["bonemeal"] = bool(p.get("bonemeal"))
        out["wait"] = _int(p.get("wait", 600), 30, 7200, "Wait between checks (seconds)")
        out["cycles"] = _int(p.get("cycles", 0), 0, 999, "Cycles")
        out["chest"] = bool(p.get("chest", True))
    elif kind == "smelter":
        out["furnaces"] = _int(p.get("furnaces", 4), 1, 16, "Furnaces")
        fuel = clean_item(p.get("fuel") or "minecraft:coal")
        if not fuel:
            raise ValueError("Pick the fuel item.")
        out["fuel"] = fuel
        out["once"] = bool(p.get("once"))
    elif kind == "hauler":
        legs = []
        for l in (p.get("legs") or []):
            if not isinstance(l, dict):
                raise ValueError("Bad leg.")
            a, b, it = (str(l.get(k) or "").strip() for k in ("from", "to", "item"))
            if not (a or b or it):
                continue                                        # an empty row
            for what, v in (("From", a), ("To", b)):
                if not v or not re.fullmatch(r"[A-Za-z0-9 _.:\-]{1,40}", v):
                    raise ValueError("%s needs the name of one of your jobs (letters, numbers, spaces)." % what)
            if it and not re.fullmatch(r"[a-z0-9_:.\-]{1,40}", it):
                raise ValueError("The item filter is part of an item name, like  log  or  charcoal.")
            legs.append({"from": a, "to": b, "item": it})
        if not legs:
            raise ValueError("Add at least one leg: where to take items from and where to put them.")
        if len(legs) > 6:
            raise ValueError("A hauler can have up to 6 legs.")
        out["legs"] = legs
        out["wait"] = _int(p.get("wait", 20), 5, 600, "Wait when idle (seconds)")
        out["cycles"] = _int(p.get("cycles", 0), 0, 9999, "Rounds")
    elif kind == "keeper":
        out["length"] = _int(p.get("length", 8), 1, 30, "Corridor length")
        out["wait"] = _int(p.get("wait", 10), 3, 300, "Wait between checks (seconds)")
        out["rescan"] = _int(p.get("rescan", 1800), 0, 86400, "Re-count every chest (seconds, 0 = never)")
    elif kind == "miner":
        out["depth"] = _int(p.get("depth", 20), 4, 120, "Depth")
        out["reach"] = _int(p.get("reach", 30), 3, 96, "Main tunnel length")
        out["rib"] = _int(p.get("rib", 12), 0, 32, "Side tunnel length")
        want = p.get("want", [k for k, _l in MINER_RESOURCES])
        if not isinstance(want, (list, tuple)) or not want or any(w not in dict(MINER_RESOURCES) for w in want):
            raise ValueError("Pick at least one resource to look for.")
        out["want"] = [k for k, _l in MINER_RESOURCES if k in want]
    elif kind == "scout":
        out["radius"] = _int(p.get("radius", 24), 4, 64, "Radius")
        out["up"] = _int(p.get("up", 8), 0, 40, "Height above the start")
        out["down"] = _int(p.get("down", 4), 0, 40, "Depth below the start")
    elif kind == "agent":
        pass
    elif kind == "foreman":
        jobs = []
        for j in (p.get("jobs") or [])[:16]:
            if not isinstance(j, dict) or j.get("kind") not in dict(AUTO_KINDS) or j.get("kind") == "foreman":
                raise ValueError("Bad job in the foreman's list.")
            slug = str(j.get("slug") or "")
            if not re.fullmatch(r"[a-z0-9_\-]{1,40}", slug):
                raise ValueError("Bad program name in the foreman's list.")
            foot = j.get("foot")
            if foot is not None:
                if not (isinstance(foot, (list, tuple)) and len(foot) == 6):
                    raise ValueError("Bad footprint in the foreman's list.")
                foot = [_int(v, -999, 999, "Footprint") for v in foot]
            kit = []
            for k in (j.get("kit") or [])[:8]:
                if not (isinstance(k, (list, tuple)) and len(k) == 2 and k[0] in KIT_TAGS):
                    raise ValueError("Bad kit in the foreman's list.")
                kit.append([k[0], _int(k[1], 0, 256, "Kit amount")])
            jobs.append({"name": clean_name(j.get("name") or slug), "slug": slug, "kind": j["kind"],
                         "furnaces": _int(j.get("furnaces", 0), 0, 16, "Furnaces"), "foot": foot,
                         "kit": kit, "crafty": bool(j.get("crafty"))})
        out["jobs"] = jobs
        out["dispatch"] = bool(p.get("dispatch", True))
        out["build"] = bool(p.get("build", True))
        for k in ("agent_url", "launcher_url"):
            v = str(p.get(k) or "")
            if v and not re.fullmatch(r"https?://[A-Za-z0-9._~:/?#@!$&'()*+,;=%\-]{1,300}", v):
                raise ValueError("Bad address for the first-start programs.")
            out[k] = v
    else:
        grid = p.get("grid") or [None] * 9
        if not isinstance(grid, list) or len(grid) != 9:
            raise ValueError("The recipe needs 9 cells.")
        cells = []
        for g in grid:
            if g in (None, "", False):
                cells.append(None)
            else:
                n = clean_item(g)
                if not n:
                    raise ValueError("Bad item in the recipe grid.")
                cells.append(n)
        if not any(cells):
            raise ValueError("Put at least one ingredient in the recipe grid.")
        out["grid"] = cells
        out["out"] = clean_item(p.get("out")) if p.get("out") else ""
        out["total"] = _int(p.get("total", 0), 0, 99999, "Crafts")
        out["once"] = bool(p.get("once"))
    return out


def _lua_value(v):
    if v is None or v is False:
        return "false"
    if v is True:
        return "true"
    if isinstance(v, (int, float)):
        return str(v)
    if isinstance(v, str):
        return json.dumps(v)
    if isinstance(v, (list, tuple)):
        return "{" + ", ".join(_lua_value(x) for x in v) + "}"
    if isinstance(v, dict):
        return "{" + ", ".join("%s = %s" % (k, _lua_value(x)) for k, x in sorted(v.items())) + "}"
    raise TypeError(v)


def auto_slug(p):
    return slugify(p["name"])


def generate_auto_lua(p, live_url=""):
    """The turtle program for one automation job."""
    p = clean_auto(p)
    tmpl = {"treefarm": AUTO_TREEFARM_TEMPLATE, "smelter": AUTO_SMELTER_TEMPLATE, "crafter": AUTO_CRAFTER_TEMPLATE,
            "scout": AUTO_SCOUT_TEMPLATE, "agent": AUTO_AGENT_TEMPLATE, "miner": AUTO_MINER_TEMPLATE, "hauler": AUTO_HAULER_TEMPLATE, "keeper": AUTO_KEEPER_TEMPLATE,
            "foreman": AUTO_FOREMAN_TEMPLATE}[p["kind"]]
    plan = {k: v for k, v in p.items() if k != "kind"}
    if p["kind"] == "crafter":
        plan.pop("out", None)
    plan["kind"] = p["kind"]
    plan["live"] = normalize_live_url(live_url)
    text = "local PLAN = " + _lua_value(plan)
    return ("-- built by Carve Designer v%s\n" % VERSION) + tmpl.replace("--@@PLAN@@", text, 1).replace("--@@COMMON@@", AUTO_COMMON_LUA, 1)


def auto_summary(p):
    """Plain words (and rough numbers) about what a job needs, shown before uploading."""
    p = clean_auto(p)
    lines, warns = [], []
    if p["kind"] == "treefarm":
        n = p["cols"] * p["rows"]
        sx = p["spacing"] * (p["cols"] + 1)
        sz = p["spacing"] * p["rows"] + 1
        lines.append("%d trees in a grid of %d x %d, about %d x %d blocks of flat ground (dirt or grass)." % (n, p["cols"], p["rows"], sx, sz))
        lines.append("Slot 1: at least %d %s. %s" % (n, dict(SAPLINGS).get(p["sapling"], p["sapling"]).lower() + " saplings"
                     if p["sapling"] in dict(SAPLINGS) else p["sapling"],
                     "Slot 2: bone meal (trees grow at once)." if p["bonemeal"] else "No bone meal: it waits %d s between rounds." % p["wait"]))
        lines.append("A chest right behind the start collects the logs." if p["chest"] else "No chest: you have to empty it.")
        lines.append("A free walkway: the column at the start and the lane in front of each row.")
        if p["spacing"] < 4:
            warns.append("Trees closer than 4 apart grow into each other.")
    elif p["kind"] == "smelter":
        lines.append("%d furnaces in a row, 2 blocks in front of the start. Run it once with  setup  and %d furnaces in its inventory to place them." % (p["furnaces"], p["furnaces"]))
        lines.append("Chest BEHIND the start: raw items + %s. Chest on the LEFT: results." % item_label(p["fuel"]))
        lines.append("One stack per furnace per round; about %d s per round for full stacks." % (64 * 10 + 6))
        lines.append("One %s smelts 8 items." % item_label(p["fuel"]).lower())
        lines.append("No coal? Give it logs: it burns about 40%% of them to make the first charcoal, and once it holds 32 charcoal it burns that instead. It keeps up to a stack of charcoal for fuel and sends the rest to the output chest.")
        lines.append("It places its own chests (digging out earth where they go) from chests in its inventory.")
    elif p["kind"] == "hauler":
        for l in p["legs"]:
            lines.append("Takes %s from the output chest of '%s' and puts it in the input chest of '%s'." % (
                ("items with '%s' in the name" % l["item"]) if l["item"] else "everything", l["from"], l["to"]))
        lines.append("It asks the app where those chests are, so it needs live reporting, its own start position, and the start positions of those jobs (Fleet tab or GPS).")
        lines.append("It stands on top of each chest, so keep the block above every chest free. It never digs.")
        lines.append("Fuel: give it some coal or charcoal; it also burns charcoal it is carrying when it runs low.")
        lines.append("Stacks that don't match the filter go straight back; if a chest has 14 or more stacks of other items in front, it may not reach the matching ones.")
        warns.append("Without live reporting nobody can tell it where the chests are.")
    elif p["kind"] == "keeper":
        lines.append("A warehouse that builds itself: a corridor of up to %d steps with 4 storage chests per step (right, left, above, below) = up to %d chests, %d stacks." % (
            p["length"], p["length"] * 4, p["length"] * 4 * 27))
        lines.append("Start it with a chest in the first slot and fuel in another. It places the DROP chest behind the start and the PICKUP chest on the left, then one storage chest at a time as it needs room.")
        lines.append("Put items in the drop chest (or let a hauler do it): they are sorted into the chests, one kind of item per chest where it can. Chests you put in there are kept and used to grow the warehouse.")
        lines.append("It remembers what is in every chest and reports it to the Storage tab of the Fleet page. Ask for an item there and it appears in the pickup chest.")
        lines.append("Needs live reporting for the web page. It digs its corridor, so pick a spot with room (about 3 wide, 3 high and %d long)." % (p["length"] + 2))
        warns.append("Without live reporting it still stores things, but you can't see or order items from the website.")
    elif p["kind"] == "miner":
        ribs = (p["reach"] // 3) * 2 if p["rib"] else 0
        fuel = 2 * p["depth"] + 2 * p["reach"] + 2 * p["rib"] * ribs
        lines.append("Digs a shaft %d blocks straight down from the start, a main tunnel %d blocks long, and %d side tunnels of %d blocks (every 3 blocks)." % (
            p["depth"], p["reach"], ribs, p["rib"]))
        lines.append("Looks for: %s. It checks every wall it passes and mines the whole vein." % ", ".join(
            dict(MINER_RESOURCES)[w].lower() for w in p["want"]))
        lines.append("Chest right BEHIND the start: it empties itself there when full and takes finds back up. Stone and dirt are thrown away.")
        lines.append("Fuel for the whole run: about %d. Give it that much coal to start; coal ore it finds refuels it." % fuel)
        lines.append("Diamonds are most common about 55-60 blocks below sea level (y = -58); coal and iron are everywhere above.")
        if fuel > 2500:
            warns.append("That is a lot of fuel (one coal gives 80). Start it with a stack of coal.")
        warns.append("Never mines next to lava on purpose, but unlit caves have mobs: place it somewhere you can defend.")
    elif p["kind"] == "scout":
        lines.append("Explores up to %d blocks around the start, %d up and %d down, and reports every block it sees to the Fleet map." % (
            p["radius"], p["up"], p["down"]))
        lines.append("It never digs, places or enters water and lava. It flies through open air and over ledges the way a turtle can.")
        lines.append("Needs fuel: coal (or logs) in its inventory. Stand it on the START cell facing forward; it returns there when done.")
        lines.append("The map needs live reporting ticked at upload, and the turtle's start position (GPS, or typed in the Fleet tab).")
        if p["radius"] > 40:
            warns.append("A big radius takes a long time and a lot of fuel.")
    elif p["kind"] == "foreman":
        lines.append("Builds the other turtles of the colony so you only start this one by hand. It crafts each turtle (computer, turtle, diamond pickaxe; crafty for the crafter) from the chest of materials behind it, places it in front, boots it with a disk drive and floppy that install the first-start programs, hands it its chests, furnaces, saplings and coal, and sends it to its job's start position.")
        lines.append("It needs a pickaxe and a crafting table: a crafty turtle, or a plain turtle with a crafting table in its inventory (it equips it itself). Put the materials listed in the Colony tab in the chest behind it, an empty chest on its left (sorting), and a few coal in its own inventory.")
        lines.append("Needs live reporting, its own start position, and the jobs' positions (stations marked in the pixel designer, or typed). Jobs without a position are laid out in a row to its right.")
        lines.append("Set 'build' off in the program (old mode) to only place chests and furnaces and use agents that are already waiting.")
        warns.append("Without live reporting it can't know where anything goes.")
    elif p["kind"] == "agent":
        lines.append("Sits idle and reports to the Fleet tab until it is told to start a program there, or by another turtle with  carve start <its id> <program>.")
        lines.append("Needs the  carve  menu installed on this turtle, and live reporting ticked at upload.")
        warns.append("Without live reporting nobody can reach it.")
    else:
        used = [g for g in p["grid"] if g]
        kinds = sorted(set(used))
        lines.append("Crafts the recipe over and over: %s." % ", ".join("%d x %s" % (used.count(k), item_label(k)) for k in kinds))
        lines.append("Needs a crafty turtle (turtle + crafting table). Ingredients in the chest BEHIND, results go to the chest on the LEFT.")
        if p["total"]:
            lines.append("Stops after %d crafts." % p["total"])
    return {"lines": lines, "warnings": warns}


# ---------------------------------------------------------------- the colony starter set
def colony_starter():
    """The four turtles that start a colony (storage keeper, tree farm, smelter, crafter) and the hauler that links them."""
    comp = dict(CRAFTER_DEFAULT, name="Compressor", grid=["minecraft:charcoal"] * 9)
    haul = dict(HAULER_DEFAULT, name="Hauler", legs=[
        {"from": "Tree farm", "to": "Smelter", "item": "log"},
        {"from": "Smelter", "to": "Compressor", "item": "charcoal"},
        {"from": "Compressor", "to": "Storage keeper", "item": "charcoal"}])
    jobs = [dict(FOREMAN_DEFAULT), dict(KEEPER_DEFAULT, name="Storage keeper"), dict(TREE_DEFAULT, name="Tree farm"),
            dict(SMELTER_DEFAULT, name="Smelter"), comp, haul]
    return colony_label([clean_auto(j) for j in jobs])


def colony_kit(job):
    """What a new turtle for this job is handed (besides coal): [[item tag, amount]]."""
    k = job["kind"]
    if k == "keeper":
        return [["chest", 8]]
    if k == "treefarm":
        return [["sapling", job["cols"] * job["rows"]]] + ([["chest", 1]] if job.get("chest") else []) + ([["bonemeal", 16]] if job.get("bonemeal") else [])
    if k == "smelter":
        return [["furnace", job["furnaces"]], ["chest", 2]]
    if k == "crafter":
        return [["chest", 2]]
    if k == "miner":
        return [["chest", 1]]
    return []


def colony_foreman(jobs):
    """The foreman job of a colony: its list of the other jobs (name, program, kind, furnaces, footprint) is rebuilt from the
    current jobs, so it always matches what is uploaded. Returns the jobs with the foreman first (added when missing)."""
    foreman = next((j for j in jobs if j["kind"] == "foreman"), None) or clean_auto(FOREMAN_DEFAULT)
    others = [j for j in jobs if j["kind"] != "foreman"]
    foreman = dict(foreman, jobs=[{"name": j["name"], "slug": auto_slug(j), "kind": j["kind"],
                                   "furnaces": j.get("furnaces", 0) if j["kind"] == "smelter" else 0,
                                   "foot": auto_footprint(j), "kit": colony_kit(j), "crafty": j["kind"] == "crafter"}
                                  for j in others if j["kind"] != "agent"])
    foreman = clean_auto(foreman)
    return colony_label([foreman] + others)


def colony_materials(jobs):
    """What the Foreman needs in its supply chest to build and equip every other turtle:
    {"items": {item: count}, "turtles": n, "crafty": n, "lines": [plain words]}. Ready-made chests, furnaces and planks are accepted too."""
    mine = [j for j in jobs if j["kind"] not in ("foreman", "agent")]
    n = len(mine)
    crafty = sum(1 for j in mine if j["kind"] == "crafter")
    kit = [colony_kit(j) for j in mine]
    chests = sum(a for ks in kit for t, a in ks if t == "chest")
    furn = sum(a for ks in kit for t, a in ks if t == "furnace")
    saplings = sum(a for ks in kit for t, a in ks if t == "sapling")
    bone = sum(a for ks in kit for t, a in ks if t == "bonemeal")
    # v7.4/v7.5: the Foreman makes one extra chest per kit carrier and one for the hopper (+2 chests); iron has +5 for the hopper, redstone has spares.
    planks = n * 8 + 2 * (-(-n // 2)) + crafty * 4 + (chests + (2 if n else 0)) * 8          # +1 chest carries each kit to its new turtle (and is taken back), +1 goes into the hopper that loads the floppy
    items = {"iron ingots": 7 * n + 5, "stone": 7 * n + 7, "redstone": n + 5, "diamonds": 3 * n,
             "glass": 6 * (-(-n // 16)) if n else 0, "logs": -(-planks // 4), "sugar cane": 3,
             "cobblestone": furn * 8, "coal": 16 * n + 16, "saplings": saplings, "bone meal": bone}
    items = {k: v for k, v in items.items() if v}
    lines = ["%d %s" % (v, k) for k, v in items.items()]
    return {"items": items, "turtles": n, "crafty": crafty, "lines": lines, "chests": chests, "furnaces": furn}


def colony_materials_text(jobs):
    """The Foreman's shopping list, in plain words."""
    m = colony_materials(jobs)
    out = ["The Foreman builds %d turtles (%d of them crafty) from what you put in its CHEST:" % (m["turtles"], m["crafty"])]
    out += ["  " + l for l in m["lines"]]
    out += ["", "  (planks, chests, furnaces, glass panes and paper are fine instead of logs, cobblestone,",
            "   glass and sugar cane; stone means smelted cobblestone.)",
            "", "Set up the Foreman like this:",
            "  - a chest with those materials BEHIND it, an empty chest on its LEFT",
            "  - a few coal in its own inventory for fuel",
            "  - free space in FRONT of it (new turtles appear there) and one block above that",
            "", "Also needed:",
            "  - the Foreman: a turtle with a pickaxe, crafted by hand, plus a crafting table (equipped, or in its inventory)",
            "  - its own start position (and the jobs' positions: marks in the pixel designer, or the Advanced list)",
            "  - 'Upload' first: new turtles download their programs from GitHub",
            "", "Then start the Foreman. Each turtle is built, started, given its items and sent to its position."]
    return "\n".join(out)


def colony_label(jobs):
    """Give every job without a turtle name the next unused Deadlock hero name (in this run's random order), so each turtle names itself on its first start."""
    used = {j.get("label") for j in jobs if j.get("label")}
    out = []
    for j in jobs:
        j = dict(j)
        if not j.get("label"):
            n, name = 1, None
            while name is None:
                for g in NAME_ORDER:
                    cand = g if n == 1 else "%s %d" % (g, n)
                    if cand not in used:
                        name = cand
                        break
                n += 1
            j["label"] = name
            used.add(name)
        out.append(j)
    return out


def colony_extra(jobs, kind):
    """One more job of this kind for a colony, with a name no other job has ("Tree farm 2")."""
    if kind not in dict(AUTO_KINDS):
        raise ValueError("Unknown job type.")
    base = auto_default(kind)
    if kind == "hauler":
        src = next((j for j in jobs if j["kind"] == "hauler"), None)
        if src:
            base["legs"] = [dict(l) for l in src["legs"]]
    if kind == "crafter":
        base["grid"] = ["minecraft:charcoal"] * 9
    taken = {j["name"].lower() for j in jobs}
    name, n = base["name"], 1
    while name.lower() in taken:
        n += 1
        name = "%s %d" % (base["name"], n)
    base["name"] = name
    return colony_label(list(jobs) + [clean_auto(base)])[-1]


def colony_test_variant(job):
    """The same job, shrunk for a quick developer test (small tree farm, short warehouse, few furnaces...)."""
    j = dict(job)
    k = j["kind"]
    if k == "treefarm":
        j.update(cols=2, rows=2, wait=60)
    elif k == "keeper":
        j.update(length=3, wait=5)
    elif k == "smelter":
        j.update(furnaces=2)
    elif k == "miner":
        j.update(depth=6, reach=10, rib=4)
    elif k == "scout":
        j.update(radius=8, up=3, down=2)
    return clean_auto(j)


# v7.8: 10 blocks between the jobs' areas (it was 3) so the sites are clearly separate.
def colony_layout(jobs, origin, gap=10):
    """World start cells for a row of jobs, all facing north, side by side along +x from `origin` (x, y, z) with a gap (10 blocks) between
    their footprints, so a single coordinate is all that has to be typed. Returns {job name: (x, y, z)}."""
    ox, oy, oz = origin
    cursor, out = ox, {}
    for j in jobs:
        f = auto_footprint(j) or [-1, -1, -1, 1, 1, 1]
        x = cursor - f[0]
        out[j["name"]] = (x, oy, oz)
        cursor = x + f[3] + 1 + gap
    return out


def mark_world_face(base_face, mark_face):
    """The compass direction of a station mark (forward / right / back / left of the base design) when the design's
    own forward points base_face."""
    order = ["north", "east", "south", "west"]
    return order[(order.index(base_face) + ("forward", "right", "back", "left").index(mark_face)) % 4]


def base_positions(design, origin, face):
    """World start cells of the jobs marked in the base design. origin = world (x, y, z) of the design's turtle start cell
    (where the Foreman stands) and face = the way it faces. Returns {job name: (x, y, z, facing)}."""
    out = {}
    for name, (x, y, z, f) in design.marks.items():
        w = local_to_world(tuple(origin) + (face,), (x - design.tx, y - design.ty, z - design.tz))
        out[name] = (w[0], w[1], w[2], mark_world_face(face, f))
    return out


COLONY_NEEDS = {
    "foreman": "a turtle with a pickaxe and a crafting table (in its inventory is fine: it equips it), a chest of materials behind it (see the list), an empty chest on its left, some coal.",
    "keeper": "8 or more chests (first slot), some coal. Start this one first.",
    "treefarm": "saplings (about 1 per tree), a chest, optionally bone meal.",
    "smelter": "2 chests, 4 furnaces, some coal.",
    "crafter": "a crafty turtle (turtle + crafting table), 2 chests.",
    "hauler": "some coal. Start it last, once the others are running and have start positions.",
    "miner": "a chest, plenty of coal.",
    "scout": "some coal.",
    "agent": "nothing; it waits for orders.",
}


def colony_guide(jobs):
    """Plain-words start-up list for a colony: what to put in each turtle and in which order to start them."""
    order = ["agent", "keeper", "treefarm", "smelter", "crafter", "miner", "scout", "hauler", "foreman"]
    lines = ["Start the Fleet server (Fleet tab) and make sure 'Include live reporting' is ticked.",
             "For each turtle: stand it on its start cell, set its start position in the Fleet tab (or use GPS), put in:", ""]
    for j in sorted(jobs, key=lambda j: order.index(j["kind"]) if j["kind"] in order else 99):
        lines.append("  %-16s carve %-16s %s" % (j["name"], slugify(j["name"]), COLONY_NEEDS.get(j["kind"], "")))
    lines += ["", "Each turtle gets a Deadlock hero's name when it first reports in.",
              "Watch them in the Fleet tab; the keeper's items are on the Storage page."]
    return "\n".join(lines)


AUTO_COMMON_LUA = r'''@@INCLUDE:auto_common.lua@@'''
AUTO_TREEFARM_TEMPLATE = r'''@@INCLUDE:auto_treefarm.lua@@'''
AUTO_SMELTER_TEMPLATE = r'''@@INCLUDE:auto_smelter.lua@@'''
AUTO_CRAFTER_TEMPLATE = r'''@@INCLUDE:auto_crafter.lua@@'''
AUTO_SCOUT_TEMPLATE = r'''@@INCLUDE:auto_scout.lua@@'''
AUTO_AGENT_TEMPLATE = r'''@@INCLUDE:auto_agent.lua@@'''
AUTO_MINER_TEMPLATE = r'''@@INCLUDE:auto_miner.lua@@'''
AUTO_HAULER_TEMPLATE = r'''@@INCLUDE:auto_hauler.lua@@'''
AUTO_KEEPER_TEMPLATE = r'''@@INCLUDE:auto_keeper.lua@@'''
AUTO_FOREMAN_TEMPLATE = r'''@@INCLUDE:auto_foreman.lua@@'''
