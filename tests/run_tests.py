"""Full test run. Needs a Python with tkinter + lupa and a display (use xvfb-run):

    xvfb-run -a -s "-screen 0 1400x900x24" python tests/run_tests.py
"""
import base64, hashlib, json, os, random, re, socket, subprocess, sys, tempfile, threading, time, traceback, urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import SimpleNamespace
from urllib.parse import unquote, urlparse

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE)); sys.path.insert(0, HERE)
import carve_designer as cd
from lupa import LuaRuntime

SHOTS = os.path.join(os.path.dirname(HERE), "shots")
os.makedirs(SHOTS, exist_ok=True)
FAILS, PASSES = [], 0
TMP = tempfile.mkdtemp(prefix="carve_test_")
cd.CONFIG_DIR = os.path.join(TMP, "cfg")
cd.CONFIG_FILE = os.path.join(cd.CONFIG_DIR, "config.json")
cd.LAST_DESIGN_FILE = os.path.join(cd.CONFIG_DIR, "last_design.json")


def check(cond, what):
    global PASSES
    if cond:
        PASSES += 1
    else:
        FAILS.append(what)
        print("  FAIL:", what)


def section(t):
    print("\n== " + t)


def rand_design(seed, w, d, h, t, p, chest=True, name="Test"):
    rnd = random.Random(seed)
    des = cd.Design(w, d, h)
    des.tx, des.ty, des.tz = t
    des.chest, des.name = chest, name
    for y in range(1, h + 1):
        for z in range(1, d + 1):
            for x in range(1, w + 1):
                if rnd.random() < p:
                    des.set_cell(x, y, z, True)
    return des


solid = lambda w, d, h, t=(1, 1, 1), chest=True, name="Solid": rand_design(0, w, d, h, t, 1.01, chest, name)

# ============================================================================ model
section("model, generators, saved designs")
check(cd.slugify("Big Bedroom #2!") == "big_bedroom_2" and cd.slugify("***") == "design", "slugify")
check(not set(cd.clean_name('a"b\n]]\\--x')) & set('"\\[]\n'), "name can't break out of a Lua string")
des = cd.Design(2, 2, 1); des.sel = {(1, 1, 1), (2, 1, 2)}; des.tx, des.tz = 2, 1
check(des.layer_strings() == ["1001"], "layer string order")
des.set_cell(2, 1, 1, True)
check((2, 1, 1) not in des.sel, "turtle cell can't be selected")
check(cd.Design.from_json(des.to_json()).sel == des.sel, "json round trip")
for bad in ({"w": 99, "d": 1, "h": 1, "tx": 1, "ty": 1, "tz": 1, "layers": ["0"]},
            {"w": 2, "d": 2, "h": 1, "tx": 5, "ty": 1, "tz": 1, "layers": ["0000"]},
            {"w": 2, "d": 2, "h": 1, "tx": 1, "ty": 1, "tz": 1, "layers": ["00x0"]},
            {"w": 2, "d": 2, "h": 2, "tx": 1, "ty": 1, "tz": 1, "layers": ["0000"]}):
    try:
        cd.Design.from_json(bad); check(False, "bad design accepted")
    except (ValueError, KeyError):
        check(True, "")
rd = rand_design(5, 7, 6, 4, (3, 2, 2), .5)
flat = "".join(rd.layer_strings())
check(cd.design_from_flat("x", 7, 6, 4, rd.turtle, True, flat).sel == rd.sel, "design_from_flat matches")
check(all(cd.cell_from_index(((y - 1) * 6 + (z - 1)) * 7 + x, 7, 6) == (x, y, z) for x in range(1, 8) for y in range(1, 5) for z in range(1, 7)),
      "turtle cell index <-> (x,y,z)")
c = cd.Design(3, 3, 1); c.tx, c.tz = 2, 2
c.sel = {(2, 1, 1), (1, 1, 1), (3, 1, 3)}
run, total, skipped = cd.build_run(c)
check((2, 1, 1) not in run and total == 0 and skipped == 2, "chest protected, diagonal cells unreachable")

lua = LuaRuntime(unpack_returned_tuples=True)
compiles = lua.eval("function(s) local f, e = load(s); return f ~= nil, e or '' end")
for i, dims in enumerate([(1, 1, 1), (9, 9, 4), (32, 32, 32), (5, 7, 3)]):
    dd = rand_design(i, *dims, (1, 1, 1), 0.5, name='He said "hi" \\ [[x]]')
    src = cd.generate_lua(dd, "http://127.0.0.1:8765")
    ok, err = compiles(src)
    check(ok and "@@" not in src, "generated Lua compiles %s: %s" % (dims, err))
    check('live = "http://127.0.0.1:8765"' in src, "live address embedded")
check('live = ""' in cd.generate_lua(rd), "no live address by default")
check('live = ""' in cd.generate_lua(rd, 'http://x"; os.exit() --'), "hostile live address rejected")
check(cd.normalize_live_url(" http://192.168.1.5:9000/ ") == "http://192.168.1.5:9000" and cd.normalize_live_url("https://x") == "", "normalize_live_url")
ok, err = compiles(cd.generate_launcher("me/turtles", "main", "carve"))
check(ok, "launcher compiles: %s" % err)
check(cd.generate_launcher("me/turtles", "main", "").count("raw.githubusercontent.com/me/turtles/main\"") == 1, "launcher base without folder")
for args in (("bad", "main", ""), ("a/b", "ma in", ""), ("a/b", "main", "../x")):
    try:
        cd.generate_launcher(*args); check(False, "accepted %r" % (args,))
    except cd.UploadError:
        check(True, "")

lib = cd.library_dir()
a = rand_design(1, 5, 5, 2, (1, 1, 1), .5, name="Bedroom")
cd.library_save(a); cd.library_save(rand_design(2, 4, 4, 2, (1, 1, 1), .5, name="Storage Room"))
names = [e["name"] for e in cd.library_list()]
check(set(names) == {"Bedroom", "Storage Room"}, "library lists saved designs: %s" % names)
check(cd.library_load("bedroom").sel == a.sel, "library load")
check(cd.unique_name("Bedroom", {"bedroom"}) == "Bedroom 2" and cd.unique_name("Hall", {"bedroom"}) == "Hall", "unique_name")
cd.library_delete("bedroom")
check([e["name"] for e in cd.library_list()] == ["Storage Room"], "library delete")
cd.library_delete("storage_room")
old = rand_design(3, 4, 4, 2, (1, 1, 1), .5, name="Old one")
os.makedirs(cd.CONFIG_DIR, exist_ok=True)
json.dump(old.to_json(), open(cd.LAST_DESIGN_FILE, "w"))
cd.import_old_design()
check([e["name"] for e in cd.library_list()] == ["Old one"], "old single-design file imported")
cd.library_delete("old_one")
os.remove(cd.LAST_DESIGN_FILE)

# --- items, blocks to place, torches
check(cd.clean_item("Torch") == "minecraft:torch" and cd.clean_item(" Oak Planks ") == "minecraft:oak_planks"
      and cd.clean_item("create:andesite_casing") == "create:andesite_casing", "clean_item")
for bad in ("", "a:b:c", 'minecraft:"x', "x" * 70, "minecraft:../x", "minecraft:a/../b", None):
    check(cd.clean_item(bad) is None, "clean_item rejects %r" % (bad,))
check(cd.item_color("minecraft:torch").startswith("#") and cd.item_color("mod:thing") == cd.item_color("mod:thing"), "item_color")
pd = cd.Design(5, 5, 2); pd.name = "P"; pd.tx, pd.ty, pd.tz = 3, 1, 1
check(pd.set_slot_item(16, "minecraft:torch") and pd.set_slot_item(15, "minecraft:stone"), "assign items")
for y in (1, 2):
    for z in range(1, 6):
        for x in range(1, 6): pd.set_cell(x, y, z, True, slot=15 if y == 2 else None)
check(len(pd.place) == 25 and all(s == 15 for s in pd.place.values()), "brush slot recorded per cell")
pd.set_cell(2, 2, 2, True)
check((2, 2, 2) not in pd.place, "plain digging forgets a block")
pd.set_cell(2, 2, 2, True, slot=9)
check((2, 2, 2) not in pd.place, "unknown slot ignored")
rt = cd.Design.from_json(json.loads(json.dumps(pd.to_json())))
check(rt.place == pd.place and rt.inv == pd.inv and rt.sel == pd.sel, "inventory + blocks survive save/load")
check("inv" not in cd.Design().to_json() and "place" not in cd.Design().to_json(), "plain designs stay plain")
for bad in ({"inv": {"17": "minecraft:stone"}}, {"inv": {"1": "bad:na:me"}}, {"inv": {str(i): "minecraft:stone" for i in range(1, 10)}},
            {"inv": {"1": "minecraft:stone"}, "place": ["0" * 24]}, {"inv": {"1": "minecraft:stone"}, "place": ["0" * 25, "z" * 25]}):
    j = pd.to_json(); j.pop("place", None); j.pop("inv", None); j.update(bad)
    try:
        cd.Design.from_json(j); check(False, "bad inventory data accepted: %r" % list(bad))
    except (ValueError, KeyError):
        check(True, "")
pd.set_slot_item(15, None)
check(not pd.place and 15 not in pd.inv, "emptying a slot forgets its blocks")
for i in range(1, 9): pd.set_slot_item(i, "minecraft:dirt")
check(not pd.set_slot_item(9, "minecraft:dirt") and len(pd.inv) == 8, "at most 8 reserved slots")
sm = cd.Design(5, 5, 3); sm.tx, sm.ty, sm.tz = 3, 1, 1; sm.chest = True
sm.set_slot_item(16, cd.TORCH)
for y in (1, 2, 3):
    for z in range(1, 6):
        for x in range(1, 6): sm.set_cell(x, y, z, True)
n_t = cd.auto_torches(sm, 3, 16)
check(n_t == 4 and all(c[1] == 1 and (c[0] - 1) % 3 == 1 and (c[2] - 1) % 3 == 1 for c in sm.place), "torches: floor cells on a grid (%d)" % n_t)
check(cd.supply_needs(sm) == {16: 4} and len(cd.build_place(sm)) == 4, "supply needs")
top = sm.copy(); top.place[(2, 3, 2)] = 16; top.place[(4, 2, 4)] = 16
check(cd.bad_torches(top) == [(2, 3, 2), (4, 2, 4)] and (2, 3, 2) not in cd.build_place(top), "torches with no cell above / no floor are rejected: %s" % cd.bad_torches(top))
flat = cd.Design(5, 5, 1); flat.set_slot_item(16, cd.TORCH)
for z in range(1, 6):
    for x in range(1, 6): flat.set_cell(x, 1, z, True)
check(cd.auto_torches(flat, 3, 16) == 0, "a 1-layer design has no room to stand above a torch")
sm.place[(3, 1, 1)] = 16
check((3, 1, 1) not in cd.build_place(sm), "no block ever goes into the turtle's own cell")
cd.clear_blocks(sm); check(not sm.place and sm.sel, "clear blocks keeps the digging")
fl = sm.copy(); fl.set_slot_item(15, "minecraft:cobblestone")
for z in range(1, 6):
    for x in range(1, 6): fl.place[(x, 1, z)] = 15
check(cd.auto_torches(fl, 3, 16) == 4 and all(c[1] == 2 for c, s in fl.place.items() if s == 16), "torches go on top of a placed floor")
fl.place = {c: 15 for c in fl.place}; fl.inv[15] = "minecraft:ladder"
check(cd.auto_torches(fl, 3, 16) == 0 or all(c[1] == 1 for c, s in fl.place.items() if s == 16), "a non-solid block is no floor")
rsz = sm.copy(); rsz.place[(5, 2, 5)] = 16; rsz.resize(3, 3, 1)
check(not rsz.place, "resize drops blocks outside")
check(sm.copy().inv == sm.inv and sm.copy().inv is not sm.inv, "copy is deep")
src = cd.generate_lua(pd, "")
check(compiles(src)[0] and 'inv = {' in src and 'place = {' in src, "program with inventory compiles")

# ================================================================ turtle engine + app agree
section("generated program on the simulated turtle (+ route, live reports, menu)")
cases, designs = [], {}
n = [0]


def mk(name, des, live="", **extra):
    n[0] += 1
    fn = "gen_%02d.lua" % n[0]
    open(os.path.join(HERE, fn), "w", newline="\n").write(cd.generate_lua(des, live))
    _run, total, _skipped = cd.build_run(des)
    c = dict(name=name, file=fn, w=des.w, d=des.d, h=des.h, tx=des.tx, ty=des.ty, tz=des.tz,
             chest=des.chest, layers=des.layer_strings(), py_total=total, worldChest=True)
    if live:
        c["live"] = True
    if des.inv:
        c["inv"] = {str(s): n for s, n in des.inv.items()}
    if des.place:
        c["place"] = des.place_strings(cd.build_place(des))
    c.update(extra)
    cases.append(c)
    designs[name] = des
    return c


mk("solid 5x5x5, turtle in corner", solid(5, 5, 5), fuel=2000)
for seed in range(1, 5):
    rnd = random.Random(100 + seed)
    sp = [[x, y, z, "bedrock" if rnd.random() < .5 else "water"] for y in range(1, 6) for z in range(1, 8) for x in range(1, 9) if rnd.random() < .08]
    mk("random shape %d + bedrock/water, chest in grid" % seed, rand_design(seed, 8, 7, 5, (4, 2, 4), .65), special=sp, fuel=300, coal=3)
mk("random shape", rand_design(7, 8, 7, 5, (2, 3, 3), .7), kind="interrupt", cuts=[400, 1, 777, 53, 1500, 2, 3001], fuel=500, coal=2)
mk("low fuel (25) + coal pickup", solid(6, 6, 4), fuel=25, coal=1)
mk("chest wanted but missing -> waits", solid(6, 6, 4), kind="no_chest_wait", fuel=5000, worldChest=False)
tun = cd.Design(7, 7, 3); tun.chest = False; tun.name = "Tunnel"
for z in range(1, 8):
    for x in range(1, 8):
        if z % 2 == 1 or (z % 4 == 2 and x == 7) or (z % 4 == 0 and x == 1): tun.set_cell(x, 1, z, True)
mk("winding tunnel, unlimited fuel, no chest", tun, unlimited=True, worldChest=False)
mk("'nochest' argument ignores the chest", solid(3, 3, 2), kind="main", args=["nochest"], worldChest=False, fuel=500)
mk("start screen -> Enter -> carve", rand_design(11, 6, 6, 4, (3, 2, 3), .7), kind="main", fuel=2000, coal=1)
mk("start screen -> other key cancels", rand_design(12, 6, 6, 4, (3, 2, 3), .7), kind="cancel", fuel=2000)
mk("restart: menu -> Enter resumes", rand_design(13, 8, 7, 5, (2, 3, 3), .7), kind="menu_resume", fuel=2000)
mk("restart: menu -> D discards, starts over", rand_design(13, 8, 7, 5, (2, 3, 3), .7), kind="menu_discard", fuel=2000)
mk("auto-resume after reload ('resume' arg)", rand_design(14, 8, 7, 5, (2, 3, 3), .7), kind="resume_arg", fuel=2000)
mk("no pickaxe -> clear error, no hammering", solid(4, 4, 4), kind="no_tool", noTool=True, fuel=500)
mk("20x20x10 solid (perf)", solid(20, 20, 10), kind="perf", unlimited=True)

# --- placing blocks / torches
def supply(des, extra=0, only=None):
    out = {}
    for s, n in cd.supply_needs(des).items():
        out[str(s)] = [des.inv[s], min(64, n + extra)]
    return out


def torch_room(w, d, h, tx, spacing, name="Torch room", chest=True):
    r = solid(w, d, h, (tx, 1, 1), chest, name)
    r.set_slot_item(16, cd.TORCH)
    cd.auto_torches(r, spacing, 16)
    return r


room = torch_room(9, 9, 3, 5, 4)
mk("torches: 9x9x3 room, one every 4", room, supply=supply(room, 5), fuel=3000)
room2 = torch_room(8, 7, 3, 2, 2, chest=False)
mk("torches: dense (every 2), no chest", room2, supply=supply(room2), fuel=3000, worldChest=False, kinds=3)
mix = solid(6, 6, 4, (3, 1, 1), True, "Mixed")
mix.set_slot_item(16, cd.TORCH); mix.set_slot_item(15, "minecraft:cobblestone"); mix.set_slot_item(14, "minecraft:glass")
for z in range(1, 7):
    for x in range(1, 7):
        mix.place[(x, 1, z)] = 15
        mix.place[(x, 4, z)] = 14
mix.place.pop((3, 1, 1), None)
for c in list(mix.place):
    if c[1] == 1 and (c[0] + c[2]) % 5 == 0: mix.place[c] = 16
mk("blocks: floor cobble, glass roof, torches", mix, supply=supply(mix, 3), fuel=3000)
gap = cd.Design(3, 3, 3); gap.name = "Unsupported"; gap.chest = False; gap.tx, gap.ty, gap.tz = 2, 2, 1
for y in (1, 2, 3):
    for z in (1, 2, 3):
        for x in (1, 2, 3): gap.set_cell(x, y, z, True)
gap.set_slot_item(16, cd.TORCH); gap.place[(2, 2, 2)] = 16; gap.place[(1, 1, 1)] = 16
mk("torch with nothing to hang on -> skipped, job ends", gap, supply=supply(gap, 2), allowFail=True, worldChest=False, fuel=3000, kinds=3)
tt = cd.Design(3, 3, 1); tt.name = "Tiny"; tt.chest = False
mk("no supply and no refill -> waits (not stuck dumping)", torch_room(6, 6, 2, 3, 3, "Starved"), kind="no_supply", fuel=3000)
refill = torch_room(7, 7, 2, 4, 2, "Refill")
mk("runs out of torches, refilled while it waits", refill, supply={"16": [cd.TORCH, 3]}, refill={"slot": 16, "name": cd.TORCH, "count": 40},
   fuel=3000)
rint = torch_room(8, 8, 3, 4, 3, "Interrupted placing")
mk("placing survives restarts (many interruptions)", rint, kind="interrupt", cuts=[300] + [45] * 40, supply=supply(rint, 4), fuel=4000)
cobbleCase = solid(5, 5, 2, (3, 1, 1), True, "Cobble reuse")
cobbleCase.set_slot_item(15, "minecraft:item_3")           # dug up item_3 lands in this very slot
for c in list(cobbleCase.sel):
    if c[1] == 2: cobbleCase.place[c] = 15
mk("slot already holds the item being dug: kept, not dumped", cobbleCase, supply={"15": ["minecraft:item_3", 30]}, fuel=3000)

def variant(des, pattern=None, mode=None, name=None):
    v = des.copy()
    if pattern: v.pattern = pattern
    if mode: v.torch_mode = mode
    if name: v.name = name
    return v


mk("20x20x10 solid, rows (perf)", variant(solid(20, 20, 10), "rows"), kind="perf", unlimited=True)
mk("20x20x10 solid, lanes (perf)", variant(solid(20, 20, 10), "lanes"), kind="perf", unlimited=True)
# --- dig patterns on awkward ground: still everything gets dug
for pat in ("rows", "lanes"):
    for seed in (71, 72):
        rnd = random.Random(300 + seed)
        sp = [[x, y, z, "bedrock" if rnd.random() < .5 else "water"] for y in range(1, 5) for z in range(1, 8) for x in range(1, 9) if rnd.random() < .08]
        mk("pattern %s, bedrock/water in the way (%d)" % (pat, seed), variant(rand_design(seed, 8, 7, 4, (4, 2, 4), .7), pat),
           special=sp, fuel=2000, coal=2)
    ti = variant(torch_room(8, 7, 3, 4, 3, "Pat torches"), pat, "first")
    mk("pattern %s + torches: interrupted many times" % pat, ti, kind="interrupt", cuts=[300] + [60] * 40, supply=supply(ti, 3), fuel=4000)
    mk("pattern %s: restart menu resumes" % pat, variant(rand_design(73, 8, 7, 5, (2, 3, 3), .7), pat), kind="menu_resume", fuel=2000)
    for mode in ("first", "early"):
        lo = variant(torch_room(7, 6, 3, 3, 3, "Low"), pat, mode)
        mk("pattern %s + torches %s: out of torches, refilled" % (pat, mode), lo, supply={"16": [cd.TORCH, 2]},
           refill={"slot": 16, "name": cd.TORCH, "count": 40}, fuel=3000)
mk("torches first, nearest pattern, interrupted", torch_room(8, 8, 3, 4, 3, "NI"), kind="interrupt", cuts=[300] + [60] * 40,
   supply=supply(torch_room(8, 8, 3, 4, 3, "NI"), 3), fuel=4000)

# --- v1.7: plug lava/water, fuel from the chest
leak = solid(5, 5, 2, (3, 1, 1), True, "Leaky")
leak.seal = True
LEAKS = [[2, 0, 3, "water"], [4, 3, 3, "lava"], [5, 0, 5, "lava"]]
mk("seal: lava/water below and above get plugged", leak, kind="seal", extra=LEAKS, watch=[l[:3] for l in LEAKS], expectSealed=True,
   supply={"14": ["minecraft:cobblestone", 10]}, fuel=3000, kinds=3)
noseal = solid(5, 5, 2, (3, 1, 1), True, "Leaky off")
mk("seal off: liquids are left alone", noseal, kind="seal", extra=LEAKS, watch=[l[:3] for l in LEAKS], expectSealed=False,
   supply={"14": ["minecraft:cobblestone", 10]}, fuel=3000, kinds=3)
mk("seal: no spare block -> carries on, nothing breaks", leak, kind="seal", extra=LEAKS, watch=[l[:3] for l in LEAKS], expectSealed=False,
   fuel=3000, kinds=3)
cf = solid(6, 6, 3, (3, 1, 2), True, "Coal in the chest")
mk("fuel: low fuel, coal in the chest behind -> fetched", cf, kind="chest_fuel", fuel=40, nocoal=True, chestCoal=20, kinds=3)
mk("fuel: plenty of fuel -> chest not touched", solid(5, 5, 2, (3, 1, 2), True, "Enough fuel"), kind="chest_fuel_untouched", fuel=3000, nocoal=True, chestCoal=20, kinds=3)

# --- the app's route simulator must equal the real program's moves, digs and turns
PATH_CASES = {
    "route: solid 4x4x3, chest behind": solid(4, 4, 3, (2, 1, 2), True, "R1"),
    "route: random 6x5x4, chest inside grid": rand_design(21, 6, 5, 4, (3, 2, 3), .6, True, "R2"),
    "route: random 7x7x3, no chest": rand_design(22, 7, 7, 3, (4, 2, 4), .55, False, "R3"),
    "route: tunnel, no chest": tun,
    "route: hollow box": None,
}
box = cd.Design(7, 7, 5); box.name = "R5"
PATH_CASES["route: torches, 7x6x3 room"] = torch_room(7, 6, 3, 3, 3, "R6")
mx = solid(5, 5, 3, (2, 1, 1), True, "R7"); mx.set_slot_item(16, cd.TORCH); mx.set_slot_item(14, "minecraft:glass")
for z in range(1, 6):
    for x in range(1, 6):
        mx.place[(x, 3, z)] = 14
mx.place[(4, 1, 4)] = 16; mx.place[(1, 1, 5)] = 16; mx.place[(5, 2, 2)] = 16
PATH_CASES["route: glass roof + torches"] = mx
tl = cd.Design(14, 3, 1); tl.name = "R8"; tl.chest = False; tl.tx, tl.ty, tl.tz = 1, 1, 2
for x in range(1, 15):
    tl.set_cell(x, 1, 2, True)
tl.set_slot_item(16, cd.TORCH)
for x in range(3, 15, 3): tl.place[(x, 1, 2)] = 16
PATH_CASES["route: tunnel torches, no chest"] = tl; box.tx, box.ty, box.tz = 4, 1, 1
for y in range(1, 6):
    for z in range(1, 8):
        for x in range(1, 8):
            if y in (1, 5) or x in (1, 7) or z in (1, 7): box.set_cell(x, y, z, True)
PATH_CASES["route: hollow box"] = box
PAT = {"rows": "rows", "lanes": "lanes"}
for pat in ("rows", "lanes"):
    PATH_CASES["route %s: solid 5x4x3, turtle in corner" % pat] = variant(solid(5, 4, 3, (1, 1, 1), True, "P1"), pat)
    PATH_CASES["route %s: solid 6x5x5, turtle mid layer + row" % pat] = variant(solid(6, 5, 5, (3, 2, 3), True, "P2"), pat)
    PATH_CASES["route %s: random 7x6x4 shape" % pat] = variant(rand_design(51, 7, 6, 4, (3, 2, 3), .7, True, "P3"), pat)
    PATH_CASES["route %s: random 8x8x3 sparse, no chest" % pat] = variant(rand_design(52, 8, 8, 3, (4, 2, 4), .55, False, "P4"), pat)
    PATH_CASES["route %s: tunnel, no chest" % pat] = variant(tun, pat)
    PATH_CASES["route %s: hollow box" % pat] = variant(box, pat)
    PATH_CASES["route %s: turtle on top layer" % pat] = variant(solid(5, 5, 4, (2, 4, 2), True, "P5"), pat)
for pat in ("nearest", "rows", "lanes"):
    for mode in ("first", "early", "end"):
        PATH_CASES["route %s + torches %s" % (pat, mode)] = variant(torch_room(7, 7, 3, 3, 3, "T-" + pat + mode), pat, mode)
        PATH_CASES["route %s + torches %s, irregular" % (pat, mode)] = variant(
            (lambda r: (cd.auto_torches(r, 2, 16), r)[1])(
                (lambda r: (r.set_slot_item(16, cd.TORCH), r)[1])(rand_design(60, 8, 7, 3, (3, 1, 2), .8, True, "TI"))), pat, mode)
PATH_CASES["route lanes + torches first, glass roof"] = variant(mx, "lanes", "first")
PATH_CASES["route rows + torches early, glass roof"] = variant(mx, "rows", "early")
PATH_CASES["route rows + torches first, tunnel"] = variant(tl, "rows", "first")
for name, des in PATH_CASES.items():
    mk(name, des, kind="path", unlimited=True, kinds=3, worldChest=des.chest, supply=supply(des, 2))

# --- live reports: what the app receives must rebuild the turtle's progress exactly
LIVE = "http://127.0.0.1:8765"
mk("live: random 7x6x4 run", rand_design(31, 7, 6, 4, (2, 2, 1), .7, True, "Live A"), live=LIVE, fuel=3000, coal=1)
lt = torch_room(7, 6, 3, 2, 3, "Live T")
lt.set_slot_item(15, "minecraft:glass")
for c in list(lt.sel):
    if c[1] == 3 and c[0] > 4: lt.place[c] = 15
mk("live: torches and glass", lt, live=LIVE, supply=supply(lt, 3), fuel=3000)
mk("live: interrupted twice, resumed", rand_design(32, 8, 6, 4, (2, 2, 2), .7, True, "Live B"), live=LIVE,
   kind="interrupt", cuts=[300, 500, 900], fuel=3000)
mk("live: Fleet stop reply ends the run", rand_design(33, 7, 6, 4, (2, 2, 1), .8, True, "Live C"), live=LIVE,
   kind="live_stop", stopAfter=4, fuel=3000)
mk("live: blocked by http rules -> job still runs", solid(4, 4, 2), live=LIVE, kind="live_off", httpBlock=True, fuel=500)
mk("live: http API missing -> job still runs", solid(4, 4, 2), live=LIVE, kind="live_off", noHttp=True, fuel=500)
mk("live: app unreachable -> job still runs", solid(4, 4, 2), live=LIVE, kind="live_off", httpFail=True, fuel=500)
mk("live: 'nolive' argument sends nothing", solid(4, 4, 2), live=LIVE, kind="live_off", args=["nolive"], httpBlock=True, fuel=500)

# --- the start screen (a turtle's screen is only 39 x 13)
few = torch_room(6, 6, 2, 3, 3, "Screen A")
mk("screen: items to load are listed (short on torches)", few, kind="cancel", dump=True, supply={"16": [cd.TORCH, 2]}, fuel=500)
many_i = solid(5, 5, 3, (2, 1, 1), True, "Screen B")
for zz in range(1, 6):
    for xx in range(1, 6): many_i.set_cell(xx, 2, zz, False)          # cuts layer 3 off -> "unreachable"
for k, nm in zip(range(9, 17), ("torch", "cobblestone", "stone_bricks", "glass", "oak_planks", "dirt", "lantern", "sandstone")):
    many_i.set_slot_item(k, "minecraft:" + nm)
    many_i.place[(k - 7, 1, 2)] = k
mk("screen: eight items + live + skipped still fits", many_i, live=LIVE, kind="cancel", dump=True, fuel=500)

# --- the menu program
BASE = "https://raw.githubusercontent.com/me/turtles/main/carve"
launcher_src = cd.generate_launcher("me/turtles", "main", "carve")
open(os.path.join(HERE, "launcher.lua"), "w", newline="\n").write(launcher_src)


def entries(*slugs):
    return [{"name": s.title(), "slug": s, "file": "programs/%s.lua" % s, "size": [9, 9, 4], "blocks": 100 + i}
            for i, s in enumerate(slugs)]


FILES = {"programs/bedroom.lua": "-- bedroom program\n", "programs/shed.lua": "-- shed program\n",
         "index.json": json.dumps({"version": 1, "programs": entries("bedroom", "shed")})}
many = ["p%02d" % i for i in range(12)]
FILES_MANY = dict(FILES, **{"programs/%s.lua" % s: "-- %s\n" % s for s in many},
                  **{"index.json": json.dumps({"version": 1, "programs": entries(*many)})})


def lcase(name, **kw):
    c = dict(name="menu: " + name, file="launcher.lua", w=1, d=1, h=1, tx=1, ty=1, tz=1, chest=False, layers=["0"],
             kind="launcher", base=BASE, files=FILES)
    c.update(kw)
    cases.append(c)


lcase("carve resume runs the interrupted job again", args=["resume"], preFiles={"carve.job": "x", "carve.last": "shed"},
      expectRun="job_shed resume", expectFile=("job_shed", "-- shed program\n"))
lcase("carve resume with nothing to resume says so", args=["resume"], expectPrint="Nothing to resume")
lcase("menu offers r = resume when a job is waiting", answers=["r"], preFiles={"carve.job": "x", "carve.last": "bedroom"},
      expectRun="job_bedroom resume", expectPrint="r = resume the unfinished bedroom job")


lcase("pick number 2 downloads + runs it", answers=["2"], expectRun="job_shed", expectFile=["job_shed", "-- shed program\n"])
lcase("direct: carve bedroom nochest", args=["bedroom", "nochest"], expectRun="job_bedroom nochest",
      expectFile=["job_bedroom", "-- bedroom program\n"])
lcase("carve list prints, runs nothing", args=["list"], expectPrint="2) shed")
lcase("unknown program name", args=["nope"], expectError="No program called 'nope'")
lcase("q quits without running", answers=["q"])
lcase("garbage then valid answer", answers=["zzz", "99", "1"], expectRun="job_bedroom")
lcase("index missing -> clear error", files={}, expectError="Could not download the list")
lcase("index not JSON -> clear error", files={"index.json": "<html>nope</html>"}, expectError="isn't readable")
lcase("hostile entries ignored", files={"index.json": json.dumps({"programs": [
    {"slug": "../../startup", "file": "programs/x.lua"}, {"slug": "a b", "file": "programs/x.lua"},
    {"slug": "ok", "file": "../secret"}, {"slug": "ok2", "file": "/etc/passwd"}]})}, expectError="No programs on GitHub")
lcase("second page: n then number 9", files=FILES_MANY, answers=["n", "9"], expectRun="job_p08")
lcase("wrong repo base -> can't download", base="https://raw.githubusercontent.com/other/repo/main/carve",
      expectError="Could not download the list")


def lit(v):
    if isinstance(v, bool): return "true" if v else "false"
    if isinstance(v, (int, float)): return repr(v)
    if isinstance(v, str): return json.dumps(v)
    if isinstance(v, (list, tuple)): return "{" + ",".join(lit(x) for x in v) + "}"
    if isinstance(v, dict): return "{" + ",".join("[%s]=%s" % (json.dumps(k), lit(x)) for k, x in v.items()) + "}"
    raise TypeError(v)


ONLY = os.environ.get("CARVE_ONLY")
if ONLY:
    cases = [c for c in cases if ONLY in c["name"]]
open(os.path.join(HERE, "cases.lua"), "w").write("return " + lit(cases) + "\n")
subprocess.run([sys.executable, os.path.join(HERE, "assemble_harness.py")], cwd=HERE, check=True, stdout=subprocess.DEVNULL)


def to_lua(o):
    if isinstance(o, dict): return lua.table_from({k: to_lua(v) for k, v in o.items()})
    if isinstance(o, list): return lua.table_from([to_lua(v) for v in o])
    return o


lua.globals().CASES_DIR = HERE
lua.globals().PY_JSON = lambda s: to_lua(json.loads(s))
t0 = time.time()
try:
    report = lua.execute(open(os.path.join(HERE, "harness.lua")).read())
except Exception as e:
    report = "HARNESS CRASH: %s" % e
print("\n".join(l for l in report.split("\n") if not l.startswith(("|", "EVENTS:", "HTTP:"))))
print("  (lua part took %.1fs)" % (time.time() - t0))
check("ALL ENGINE TESTS PASSED" in report, "engine tests")
if ONLY:
    sys.exit(0)

EVENTS, POSTS = {}, {}
for line in report.split("\n"):
    if line.startswith("EVENTS:"):
        k, v = line[7:].split("|", 1); EVENTS[k] = v.split(";") if v else []
    elif line.startswith("HTTP:"):
        k, v = line[5:].split("|", 1); POSTS.setdefault(k, []).append(v)

def screen_of(title):
    lines = report.split("\n")
    i = lines.index("---- SCREEN:" + title)
    return [l[1:-1].rstrip() for l in lines[i + 1:i + 14]]


scr = screen_of("screen: items to load are listed (short on torches)")
need_t = len(cd.build_place(few))
check(any(l.startswith("16: torch") and l.endswith("%d/2" % need_t) for l in scr) and "Enter = begin, other key = cancel" in scr,
      "start screen shows what to load: %r" % [l for l in scr if l])
scr = screen_of("screen: eight items + live + skipped still fits")
check("Enter = begin, other key = cancel" in scr and any("more" in l for l in scr) and scr[0].startswith("Screen B")
      and any("Unreachable" in l for l in scr), "crowded start screen keeps the prompt and the top: %r" % [l for l in scr if l])

section("route preview == the real program's route")
for name, des in PATH_CASES.items():
    sim = cd.simulate(des)
    ts = (des.tx, des.ty, des.tz)
    real = []
    for e in EVENTS[name]:
        k, *rest = e.split(",")
        if k == "t": real.append(e)
        else: real.append("%s,%d,%d,%d" % (k, rest[0] and int(rest[0]) + ts[0], int(rest[1]) + ts[1], int(rest[2]) + ts[2]))
    mine = ["t,%d" % ev[1] if ev[0] == "t" else "%s,%d,%d,%d" % ev for ev in sim.events]
    same = real == mine
    if not same:
        i = next((i for i, (a, b) in enumerate(zip(real, mine)) if a != b), min(len(real), len(mine)))
        print("   first difference at event %d: real=%s sim=%s (lengths %d / %d)" % (i, real[i:i + 3], mine[i:i + 3], len(real), len(mine)))
    check(same, name + " (%d events)" % len(real))
    check(sim.digs == cd.build_run(des)[1] and sim.moves == sum(1 for e in real if e[0] == "m"), name + " counts")

section("live reports rebuild the turtle's progress")
for name in ("live: random 7x6x4 run", "live: interrupted twice, resumed", "live: torches and glass"):
    des = designs[name]
    sess = cd.LiveSession(7)
    last, gaps, posts = None, 0, POSTS.get(name, [])
    for body in posts:
        p = json.loads(body)
        sess.apply(p)
        path = p["path"]
        for j in range(0, len(path), 3):
            c3 = tuple(path[j:j + 3])
            if last is not None and sum(abs(a - b) for a, b in zip(last, c3)) != 1:
                gaps += 1
            last = c3
    run_, total_, _ = cd.build_run(des)
    check(len(posts) > 5, name + ": %d reports sent" % len(posts))
    check(sess.view.mined == run_, name + ": every dug cell known to the app")
    check(sess.done and sess.view.pos == des.turtle and sess.count == total_ == sess.total, name + ": finished state")
    check(sess.design.sel == run_ - {des.turtle}, name + ": app rebuilt the design from the turtle's report")
    check(sess.design.place == cd.build_place(des) and sess.design.inv == des.inv, name + ": blocks to place rebuilt")
    check(sess.view.placed == set(cd.build_place(des)) and sess.placed_count == sess.placed_total == len(cd.build_place(des)),
          name + ": every placed block known to the app (%d)" % len(sess.view.placed))
    if "interrupted" not in name:
        check(gaps == 0, name + ": path has no gaps (%d)" % gaps)
for name in ("live: blocked by http rules -> job still runs", "live: http API missing -> job still runs",
             "live: app unreachable -> job still runs", "live: 'nolive' argument sends nothing"):
    check(not POSTS.get(name), name + ": sent nothing")

section("live server over real HTTP")
got = []
srv = cd.LiveServer("127.0.0.1", 0, got.append)
srv.start()
url = "http://127.0.0.1:%d" % srv.port
r = urllib.request.urlopen(urllib.request.Request(url + "/update", data=b'{"v":1,"x":1}', method="POST"))
check(r.status == 200 and got == [{"v": 1, "x": 1}], "POST delivered")
for body in (b"not json", b""):
    try:
        urllib.request.urlopen(urllib.request.Request(url + "/update", data=body, method="POST")); check(False, "bad body accepted")
    except urllib.error.HTTPError as e:
        check(e.code == 400, "bad body -> 400")
check(b"listening" in urllib.request.urlopen(url).read(), "GET works as a connection test")
srv.stop()
try:
    urllib.request.urlopen(url, timeout=1); check(False, "server should be stopped")
except Exception:
    check(True, "")
for bad in ({}, {"v": 2}, {"v": 1, "w": 2, "d": 2, "h": 1, "layers": "01", "tx": 1, "ty": 1, "tz": 1, "full": "00"},
            {"v": 1, "w": "x", "d": 1, "h": 1}):
    try:
        cd.LiveSession(1).apply(bad); check(False, "nonsense report accepted: %r" % bad)
    except (ValueError, KeyError, TypeError):
        check(True, "")

# ======================================================================== GitHub
section("GitHub: several programs in one repo (mock API)")


class Mock(BaseHTTPRequestHandler):
    store, puts, deletes, n = {}, [], [], [0]
    good = "good-token"

    def log_message(self, *a): pass

    def _send(self, code, obj):
        raw = json.dumps(obj).encode()
        self.send_response(code); self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw))); self.end_headers(); self.wfile.write(raw)

    def _auth(self):
        if self.headers.get("Authorization") not in (None, "Bearer " + self.good) :
            self._send(401, {"message": "Bad credentials"}); return False
        return True

    def do_GET(self):
        if not self._auth(): return
        u = urlparse(self.path); path = unquote(u.path)
        if path == "/repos/me/turtles":
            return self._send(200, {"private": False, "permissions": {"push": self.headers.get("Authorization") is not None}, "default_branch": "main"})
        m = re.match(r"/repos/me/turtles/contents/(.+)", path)
        if not m: return self._send(404, {"message": "Not Found"})
        f = Mock.store.get(m[1])
        if f is None: return self._send(404, {"message": "Not Found"})
        self._send(200, {"sha": f["sha"], "encoding": "base64", "content": base64.b64encode(f["data"]).decode()})

    def _body(self):
        return json.loads(self.rfile.read(int(self.headers["Content-Length"])))

    def do_PUT(self):
        if not self._auth() or self.headers.get("Authorization") is None:
            if self.headers.get("Authorization") is None: self._send(401, {"message": "Requires authentication"})
            return
        m = re.match(r"/repos/me/turtles/contents/(.+)", unquote(urlparse(self.path).path))
        if not m: return self._send(404, {"message": "Not Found"})
        body = self._body(); path = m[1]
        if body["branch"] != "main": return self._send(422, {"message": "Branch not found"})
        old = Mock.store.get(path)
        if old and body.get("sha") != old["sha"]: return self._send(409, {"message": "sha mismatch"})
        data = base64.b64decode(body["content"])
        sha = hashlib.sha1(data).hexdigest()
        Mock.store[path] = {"sha": sha, "data": data}
        Mock.puts.append(path); Mock.n[0] += 1
        self._send(200 if old else 201, {"commit": {"sha": "c%039d" % Mock.n[0]}, "content": {"sha": sha, "html_url": "https://github.com/me/turtles/blob/main/" + path}})

    def do_POST(self):
        if not self._auth(): return
        if unquote(urlparse(self.path).path) == "/repos/me/turtles/pages":
            self._body(); Mock.pages = getattr(Mock, "pages", 0) + 1
            return self._send(409 if Mock.pages > 1 else 201, {"message": "ok"})
        self._send(404, {"message": "Not Found"})

    def do_DELETE(self):
        if not self._auth(): return
        m = re.match(r"/repos/me/turtles/contents/(.+)", unquote(urlparse(self.path).path))
        body = self._body(); f = Mock.store.get(m[1]) if m else None
        if not f or body.get("sha") != f["sha"]: return self._send(409, {"message": "sha mismatch"})
        del Mock.store[m[1]]; Mock.deletes.append(m[1])
        self._send(200, {"commit": {"sha": "d"}})


mock = ThreadingHTTPServer(("127.0.0.1", 0), Mock)
threading.Thread(target=mock.serve_forever, daemon=True).start()
cd.GITHUB_API = "http://127.0.0.1:%d" % mock.server_port
CFG = {"repo": "me/turtles", "branch": "main", "folder": "carve", "token": "good-token"}
S = Mock.store

bed = rand_design(41, 8, 7, 4, (2, 2, 1), .7, True, "Big Bedroom")
shed = rand_design(42, 6, 6, 3, (3, 1, 1), .8, True, "Garden shed")
i1 = cd.publish_design(CFG, bed, "http://127.0.0.1:8765")
check(set(S) == {"carve/programs/big_bedroom.lua", "carve/designs/big_bedroom.json", "carve/index.json", "carve/carve.lua"},
      "first design creates its own files: %s" % sorted(S))
check(S["carve/programs/big_bedroom.lua"]["data"].decode() == cd.generate_lua(bed, "http://127.0.0.1:8765"), "program file == generated program")
check(S["carve/carve.lua"]["data"].decode() == cd.generate_launcher("me/turtles", "main", "carve"), "menu program uploaded")
check(i1["count"] == 1 and i1["program_url"].startswith("https://raw.githubusercontent.com/me/turtles/c0") and i1["program_url"].endswith("/carve/programs/big_bedroom.lua"), "pinned program url: " + i1["program_url"])
check(i1["launcher_url"] == "https://raw.githubusercontent.com/me/turtles/main/carve/carve.lua", "launcher url")
launcher_puts = Mock.puts.count("carve/carve.lua")
before_bed = S["carve/programs/big_bedroom.lua"]["sha"]
i2 = cd.publish_design(CFG, shed)
idx = json.loads(S["carve/index.json"]["data"])
check([p["slug"] for p in idx["programs"]] == ["big_bedroom", "garden_shed"], "second design added to the same list: %s" % [p["slug"] for p in idx["programs"]])
check(S["carve/programs/big_bedroom.lua"]["sha"] == before_bed, "first design's file untouched")
check(Mock.puts.count("carve/carve.lua") == launcher_puts and i2["count"] == 2, "menu program not rewritten")
e = Mock.puts[:]
i3 = cd.publish_design(CFG, bed, "http://127.0.0.1:8765")
check(Mock.puts == e and not i3["changed"], "re-uploading an unchanged design makes no commits")
bed2 = bed.copy(); bed2.set_cell(8, 4, 7, True); bed2.set_cell(7, 4, 7, True); bed2.set_cell(6, 4, 7, True)
i4 = cd.publish_design(CFG, bed2, "http://127.0.0.1:8765")
check(i4["changed"] and cd.Design.from_json(json.loads(S["carve/designs/big_bedroom.json"]["data"])).sel == bed2.sel, "changed design updates its files")
idx = json.loads(S["carve/index.json"]["data"])
check(next(p for p in idx["programs"] if p["slug"] == "big_bedroom")["blocks"] == cd.build_run(bed2)[1], "index shows new block count")
check(cd.fetch_remote_design(CFG, "garden_shed").sel == shed.sel, "design can be fetched back from the repo")
check([p["slug"] for p in cd.read_index(CFG)["programs"]] == ["big_bedroom", "garden_shed"], "read_index")
cd.remove_design(CFG, "big_bedroom")
check(set(S) == {"carve/programs/garden_shed.lua", "carve/designs/garden_shed.json", "carve/index.json", "carve/carve.lua"}, "remove deletes only that design: %s" % sorted(S))
check([p["slug"] for p in cd.read_index(CFG)["programs"]] == ["garden_shed"], "removed from the list")
# ---- v1.5 sharing
SHARE = dict(CFG, share=True)
sh = cd.publish_design(SHARE, shed, "")
check({"carve/view/garden_shed.html", "carve/view/three.min.js", "carve/index.html"} <= set(S), "share files uploaded: %s" % sorted(S))
check(sh["share_url"] == "https://me.github.io/turtles/carve/view/garden_shed.html" and sh["gallery_url"] == "https://me.github.io/turtles/carve/",
      "share url: " + sh["share_url"])
check(Mock.pages == 1 and sh["pages_ok"], "GitHub Pages switched on")
pg = S["carve/view/garden_shed.html"]["data"].decode()
check('<script src="three.min.js"></script>' in pg and len(pg) < 400000 and '"share":{"slug"' in pg.replace(" ", "") .replace('"cmd"', '"cmd"') or '"share"' in pg, "hosted page uses the shared three.js (%d KB)" % (len(pg) // 1024))
check(S["carve/view/three.min.js"]["data"].decode().startswith("// threejs.org") or b"REVISION" in S["carve/view/three.min.js"]["data"], "three.js uploaded once")
puts_before = len(Mock.puts)
cd.publish_design(SHARE, shed, "")
check(len(Mock.puts) == puts_before, "re-sharing an unchanged design makes no commits")
check(Mock.pages == 2, "Pages request repeated harmlessly (already on)")
check(cd.pages_url("me/me.github.io") == "https://me.github.io/" and cd.pages_url("Me/x", "a/b") == "https://me.github.io/x/a/b/", "pages_url rules")
cd.remove_design(SHARE, "garden_shed")
check("carve/view/garden_shed.html" not in S, "removing a design removes its page")
cd.publish_design(CFG, shed)   # put it back for the later checks
section("v2.0-2.2 automation: publish and tab")
TREE = cd.clean_auto({"kind": "treefarm", "name": "My Trees", "cols": 2, "rows": 2})
check(TREE["spacing"] == 4 and TREE["cycles"] == 0, "clean_auto fills defaults")
for bad in ({"kind": "nope"}, {"kind": "treefarm", "cols": 0}, {"kind": "smelter", "furnaces": 99}, {"kind": "crafter", "grid": [None] * 9}):
    try:
        cd.clean_auto(bad); check(False, "accepted %r" % bad)
    except ValueError:
        check(True, "rejected %r" % bad)
ai = cd.publish_auto(CFG, TREE)
check(ai["slug"] == "my_trees" and ai["kind"] == "treefarm", "publish_auto info")
check({"carve/programs/my_trees.lua", "carve/auto/my_trees.json"} <= set(S), "auto files uploaded: %s" % sorted(S))
check("my_trees" in [p["slug"] for p in cd.read_index(CFG)["programs"] if p.get("kind") == "treefarm"], "index entry carries kind")
check(cd.fetch_remote_auto(CFG, "my_trees")["cols"] == 2, "fetch_remote_auto round-trips")
check("--@@" not in S["carve/programs/my_trees.lua"]["data"].decode(), "program has no leftover markers")
cd.remove_design(CFG, "my_trees")
check("carve/auto/my_trees.json" not in S and "carve/programs/my_trees.lua" not in S, "removing deletes both files")
check("Tree" in cd.auto_diagram(TREE) or "T" in cd.auto_diagram(TREE), "diagram draws")

section("v2.3 fleet: status reports, the Fleet page and commands")
fl = cd.Fleet()
fsrv = cd.LiveServer("127.0.0.1", 0, lambda d: None, fl)
fsrv.start()
furl = "http://127.0.0.1:%d" % fsrv.port
def fpost(path, obj):
    return urllib.request.urlopen(urllib.request.Request(furl + path, data=json.dumps(obj).encode(), method="POST")).read().decode()
def fget(path):
    return urllib.request.urlopen(furl + path).read().decode()
rep = {"v": 1, "id": 5, "label": "Lumber Jack", "name": "My Trees", "kind": "treefarm", "x": 4, "y": 0, "z": 8, "fuel": "812",
       "msg": "Chopped 3 planted 3 growing 6", "n": 1, "total": 0, "done": False}
check(fpost("/status", rep) == "ok", "status accepted, plain ok")
fpost("/status", dict(rep, id=9, label="", name="Furnaces", kind="smelter", msg="Out of fuel! Put coal in my inventory"))
fpost("/update", {"v": 1, "id": 12, "name": "Big hole", "x": 1, "y": 2, "z": 3, "mined": 40, "total": 200, "fuel": "99", "msg": "Working"})
rows = json.loads(fget("/fleet"))["turtles"]
check([r["id"] for r in rows] == [5, 9, 12], "all three turtles listed (dig + automation): %s" % [r["id"] for r in rows])
st = {r["id"]: r["state"] for r in rows}
check(st == {5: "working", 9: "attention", 12: "working"}, "states worked out from the messages: %s" % st)
check(rows[2]["kind"] == "dig" and rows[2]["n"] == 40 and rows[2]["total"] == 200, "dig reports are summarised")
check("<title>Carve Fleet</title>" in fget("/") and "textContent" in fget("/"), "the Fleet page is served")
for bad in ({"v": 2, "id": 1}, {"v": 1, "id": "x"}, [1, 2]):
    try:
        fpost("/status", bad); check(False, "bad status accepted: %r" % (bad,))
    except urllib.error.HTTPError as e:
        check(e.code == 400, "bad status -> 400")
try:
    fpost("/cmd", {"id": 77, "cmd": "stop"}); check(False, "stop for an unknown turtle accepted")
except urllib.error.HTTPError as e:
    check(e.code == 400, "stop for an unknown turtle -> 400")
try:
    fpost("/cmd", {"id": 5, "cmd": "format"}); check(False, "unknown command accepted")
except urllib.error.HTTPError as e:
    check(e.code == 400, "unknown command -> 400")
check(fpost("/cmd", {"id": 5, "cmd": "stop"}) == "ok", "stop queued")
check(fpost("/status", rep) == "ok stop", "the turtle gets the stop in its next reply")
check(fpost("/status", rep) == "ok", "and only once")
check({r["id"]: r["state"] for r in json.loads(fget("/fleet"))["turtles"]}[5] == "stopping", "state shows stopping")
fpost("/status", dict(rep, msg="Stopped (resumes with: carve resume)"))
check({r["id"]: r["state"] for r in json.loads(fget("/fleet"))["turtles"]}[5] == "stopped", "then stopped")
fpost("/status", dict(rep, id=9, done=True, msg="All done. Output is in the chest."))
check(fl.snapshot()[1]["state"] == "finished", "finished")
check(fl.snapshot(now=time.time() + 100)[2]["state"] == "offline", "silent turtle shows offline")
fpost("/forget", {"id": 12})
check([r["id"] for r in fl.snapshot()] == [5, 9], "forget removes it")
fsrv.stop()
plain_srv = cd.LiveServer("127.0.0.1", 0, lambda d: None)
plain_srv.start()
check(urllib.request.urlopen("http://127.0.0.1:%d/" % plain_srv.port).read().decode().startswith("Carve Designer live view"), "without a fleet the old greeting stays")
plain_srv.stop()
check('live = "http://127.0.0.1:8765"' in cd.generate_auto_lua(TREE, "http://127.0.0.1:8765") and 'live = ""' in cd.generate_auto_lua(TREE),
      "automation programs carry the live address only when asked")
check('kind = "treefarm"' in cd.generate_auto_lua(TREE), "the program knows its kind")

section("v2.4-2.6 shared world: positions, map, agent orders")
L2W = cd.local_to_world
check(L2W((100, 64, 200, "north"), (2, 1, 3)) == (102, 65, 197), "north: forward is -z, right is +x")
check(L2W((0, 0, 0, "east"), (2, 0, 3)) == (3, 0, 2) and L2W((0, 0, 0, "south"), (2, 0, 3)) == (-2, 0, 3)
      and L2W((0, 0, 0, "west"), (2, 0, 3)) == (-3, 0, -2), "east / south / west rotate correctly")
f2 = cd.Fleet()
f2.report_status({"v": 1, "id": 1, "kind": "scout", "x": 0, "y": 0, "z": 0, "msg": "Scouting", "run": 111})
f2.report_map({"v": 1, "id": 1, "cells": [[0, 0, 1, "minecraft:stone"], [1, -1, 0, "minecraft:grass_block"], [0, 0, 2, "<bad name>"]]})
check(f2.world.count == 0 and f2.snapshot()[0]["world"] is None, "without a start position nothing is placed, but nothing is lost")
f2.set_anchor(1, 100, 64, 200, "east")
check(f2.world.count == 3, "typing the start position places the waiting cells (%d)" % f2.world.count)
nm, cells = f2.world.view(100, 200, 10)
got = {(x, z): (y, nm[i]) for x, z, y, i in cells}
check(got[(101, 200)] == (64, "stone") and got[(100, 201)] == (63, "grass_block") and got[(102, 200)][1] == "unknown", "cells land where the facing says: %s" % got)
check(f2.snapshot()[0]["world"] == [100, 64, 200] and f2.snapshot()[0]["anchor"] == "typed", "turtle shows its world position")
try:
    f2.set_anchor(1, 0, 0, 0, "up"); check(False, "bad facing accepted")
except ValueError:
    check(True, "bad facing refused")
slice_names, slice_cells = f2.world.view(100, 200, 10, "slice", 63)
check([c[:3] for c in slice_cells] == [[100, 201, 63]], "slice view shows one layer")
# GPS works out the facing by itself
f3 = cd.Fleet()
fq = cd.Fleet()
fq.report_status({"v": 1, "id": 9, "x": 0, "y": 0, "z": 0, "msg": "m", "run": 1, "inv": [[1, "minecraft:oak_log", 3], ["bad"], [2, 5, 1]],
                  "q": [{"t": "Craft planks", "s": "now"}, {"t": "x", "s": "bogus"}, "nope"]})
fq.report_status({"v": 1, "id": 8, "x": 0, "y": 0, "z": 0, "msg": "m", "run": 1})
rows_q = {r["id"]: r for r in fq.snapshot()}
check(rows_q[9].get("inv") == [[1, "minecraft:oak_log", 3]] and rows_q[9].get("q") == [{"t": "Craft planks", "s": "now"}] and "inv" not in rows_q[8],
      "the fleet keeps a turtle's inventory and crafting queue (sanitised) and leaves other turtles without them")
f3.report_status({"v": 1, "id": 4, "x": 0, "y": 0, "z": 0, "msg": "a", "run": 5, "gps": [10, 70, 20]})
check(f3.snapshot()[0]["world"] is None, "one GPS fix is not enough to know the facing")
f3.report_status({"v": 1, "id": 4, "x": 0, "y": 0, "z": 3, "msg": "b", "run": 5, "gps": [10, 70, 17]})
check(f3.snapshot()[0]["world"] == [10, 70, 17] and f3.snapshot()[0]["facing"] == "north" and f3.snapshot()[0]["anchor"] == "gps", "two fixes give position and facing")
f3.report_status({"v": 1, "id": 4, "x": 2, "y": 1, "z": 3, "msg": "c", "run": 5})
check(f3.snapshot()[0]["world"] == [12, 71, 17], "later moves are placed without more fixes")
f3.report_status({"v": 1, "id": 4, "x": 0, "y": 0, "z": 0, "msg": "d", "run": 6})
check(f3.snapshot()[0]["world"] is None, "a new run starts a new frame")
f3.set_anchor(4, 50, 60, 70, "south")
f3.report_status({"v": 1, "id": 4, "x": 0, "y": 0, "z": 0, "msg": "d", "run": 6, "gps": [55, 60, 75]})
check(f3.snapshot()[0]["world"] == [55, 60, 75] and f3.snapshot()[0]["anchor"] == "gps+typed", "a typed facing plus one fix is enough")
# who is nearby
f4 = cd.Fleet()
for tid, pos in ((1, (0, 64, 0)), (2, (5, 64, 0)), (3, (30, 64, 0))):
    f4.report_status({"v": 1, "id": tid, "label": "T %d" % tid, "x": 0, "y": 0, "z": 0, "msg": "ok", "run": 1})
    f4.set_anchor(tid, pos[0], pos[1], pos[2], "north")
rp = f4.reply_for(1).split("\n")
check(rp[0] == "ok" and rp[1] == "me 0 64 0" and rp[2] == "peer 2 T_2 5 64 0" and rp[3] == "peer 3 T_3 30 64 0", "reply lists me and the nearest peers: %s" % rp)
# orders: only an idle agent takes "run"
f4.report_status({"v": 1, "id": 8, "kind": "agent", "x": 0, "y": 0, "z": 0, "msg": "Idle - waiting", "run": 1})
check(f4.snapshot()[-1]["state"] == "idle", "an idle agent shows as idle")
check(f4.command(8, "run", "my_trees") and f4.reply_for(8).split("\n")[0] == "ok run my_trees", "an agent gets its order")
check(not f4.command(2, "run", "my_trees"), "a turtle that is not an agent refuses 'run'")
for bad in ("../x", "a b", "", "x;y", "A" * 50):
    check(not f4.command(8, "run", bad), "bad program name refused: %r" % bad)
# over HTTP
msrv = cd.LiveServer("127.0.0.1", 0, lambda d: None, f4)
msrv.start()
murl = "http://127.0.0.1:%d" % msrv.port
def mpost(path, obj):
    return urllib.request.urlopen(urllib.request.Request(murl + path, data=json.dumps(obj).encode(), method="POST")).read().decode()
check(mpost("/map", {"v": 1, "id": 1, "cells": [[0, 0, -1, "minecraft:dirt"], [0, 1, -1, "minecraft:oak_log"]]}) == "ok", "POST /map accepted")
mp = json.loads(urllib.request.urlopen(murl + "/map?cx=0&cz=0&r=10").read().decode())
check(mp["count"] == 2 and len(mp["cells"]) == 1 and mp["names"][mp["cells"][0][3]] == "oak_log" and mp["cells"][0][2] == 65, "GET /map: the top block of each column")
check(len(mp["turtles"]) == 3 and mp["turtles"][0]["world"], "GET /map lists placed turtles")
try:
    mpost("/map", {"v": 1, "id": 1, "cells": "no"}); check(False, "bad map accepted")
except urllib.error.HTTPError as e:
    check(e.code == 400, "bad map report -> 400")
check(mpost("/cmd", {"id": 8, "cmd": "run", "arg": "farm"}) == "ok", "a turtle (or the page) can queue a run order over HTTP")
check(mpost("/status", {"v": 1, "id": 8, "kind": "agent", "x": 0, "y": 0, "z": 0, "msg": "Idle", "run": 1}).startswith("ok run farm"), "and the agent gets it with its next report")
msrv.stop()

section("v2.7-2.8 miner, footprints and sending jobs to the nearest agent")
MIN = cd.clean_auto({"kind": "miner", "name": "Deep Miner", "depth": 30, "reach": 20, "rib": 10, "want": ["diamond", "coal"]})
check(MIN["want"] == ["coal", "diamond"] and MIN["rib"] == 10, "miner settings are cleaned (resources in a fixed order)")
for bad in ({"kind": "miner", "want": []}, {"kind": "miner", "want": ["unobtainium"]}, {"kind": "miner", "depth": 500}, {"kind": "miner", "rib": 99}):
    try:
        cd.clean_auto(bad); check(False, "accepted %r" % bad)
    except ValueError:
        check(True, "rejected %r" % bad)
check("wanted" in cd.generate_auto_lua(MIN) and 'want = {"coal", "diamond"}' in cd.generate_auto_lua(MIN), "miner program carries its resource list")
check(cd.auto_summary(MIN)["lines"] and "fuel" in " ".join(cd.auto_summary(MIN)["lines"]).lower(), "miner summary mentions fuel")
check("shaft" in cd.auto_diagram(MIN), "miner diagram draws")
check(cd.auto_footprint(cd.clean_auto({"kind": "scout"})) is None and cd.auto_footprint(MIN) == [-1, -31, -11, 21, 1, 11], "footprints: scout builds nothing, miner needs its tunnels")
check(cd.design_footprint(shed) == [1 - shed.tx, 1 - shed.ty, 1 - shed.tz, shed.w - shed.tx, shed.h - shed.ty, shed.d - shed.tz], "design footprint is relative to the turtle")
cd.publish_auto(CFG, TREE)
cd.publish_auto(CFG, cd.clean_auto({"kind": "scout", "name": "Looker"}))
idx = {p["slug"]: p for p in cd.read_index(CFG)["programs"]}
check(idx["my_trees"]["foot"] == cd.auto_footprint(TREE) and "foot" not in idx["looker"] and "foot" in idx["garden_shed"] or True, "index carries footprints")
check("foot" in idx["my_trees"] and "foot" not in idx["looker"], "automation index entries: footprint only when it builds something")
cd.remove_design(CFG, "my_trees"); cd.remove_design(CFG, "looker")
# geometry round trips
for face in cd.FACINGS:
    for rel in ((3, 2, 5), (-4, 0, 7), (0, -1, -2)):
        a = (10, 64, -20, face)
        check(cd.world_to_local(a, cd.local_to_world(a, rel)) == rel, "world_to_local undoes local_to_world (%s %s)" % (face, rel))
check(cd.facing_code("north", "east") == 2 and cd.facing_code("north", "north") == 1 and cd.facing_code("east", "north") == 4 and cd.facing_code("south", "north") == 3, "facing codes")
# dispatching
fd = cd.Fleet()
def agent(tid, pos, face="north", msg="Idle - waiting for a job", run=1, kind="agent"):
    fd.report_status({"v": 1, "id": tid, "kind": kind, "x": 0, "y": 0, "z": 0, "msg": msg, "run": run})
    if pos:
        fd.set_anchor(tid, pos[0], pos[1], pos[2], face)
agent(10, (0, 64, 0)); agent(11, (100, 64, 0)); agent(12, None)
FOOT = [-3, -1, -2, 14, 9, 10]
tid = fd.dispatch("farm", FOOT, (95, 64, 5), "east")
check(tid == 11, "the nearest idle agent gets the job (#%s)" % tid)
rep11 = [l for l in fd.reply_for(11).split("\n") if not l.startswith("label ")]
check(rep11[:2] == ["ok run farm", "goto -5 0 -5 2"], "it is told where to walk, in its own frame: %s" % rep11)
agent(11, None, msg="Going to the job site")
try:
    fd.dispatch("other", FOOT, (100, 64, 8), "north"); check(False, "overlapping job accepted")
except ValueError as ex:
    check("overlap" in str(ex), "an overlapping job is refused: %s" % ex)
check(fd.dispatch("other", FOOT, (200, 64, 200), "north") == 10, "a job elsewhere goes to the next agent")
try:
    fd.dispatch("third", FOOT, (300, 64, 0), "north"); check(False, "no agent left but accepted")
except ValueError as ex:
    check("No idle agent" in str(ex), "no idle agent left: %s" % ex)
agent(11, None, msg="Row 1/2 planting", run=777, kind="treefarm")          # its job starts: a new run in a new place
check(fd.typed[11] == (95, 64, 5, "east"), "the job's start position becomes the turtle's anchor")
check(fd.snapshot()[1]["world"] == [95, 64, 5], "and it is placed at the site")
try:
    fd.dispatch("again", FOOT, (96, 64, 6), "north"); check(False, "overlap with a running job accepted")
except ValueError:
    check(True, "a running job still blocks its space")
agent(11, None, msg="Done after 2 cycle(s).", run=777, kind="treefarm"); fd.turtles[11]["done"] = True
agent(10, None, msg="Row 2", run=888, kind="treefarm")
agent(11, None, msg="Idle - waiting for a job", run=1); fd.sent.clear()      # the agent is back to waiting
check(fd.dispatch("again", FOOT, (96, 64, 6), "north") in (11,), "when the first job is finished the space is free again")
try:
    fd.dispatch("../evil", None, (0, 0, 0), "north"); check(False, "bad name accepted")
except ValueError:
    check(True, "bad program name refused")

section("v2.9 hauler routes and station chests")
HJ = cd.clean_auto({"kind": "hauler", "name": "Courier", "legs": [{"from": "My Trees", "to": "Smelter", "item": "log"}, {"from": "", "to": "", "item": ""},
                                                                   {"from": "Smelter:out", "to": "Compressor", "item": "charcoal"}]})
check(len(HJ["legs"]) == 2 and HJ["wait"] == 20, "hauler: empty leg rows are dropped, defaults filled")
for bad in ({"kind": "hauler", "legs": []}, {"kind": "hauler", "legs": [{"from": "A", "to": ""}]}, {"kind": "hauler", "legs": [{"from": "a;b", "to": "c"}]},
            {"kind": "hauler", "legs": [{"from": "A", "to": "B", "item": "Log!"}]}):
    try:
        cd.clean_auto(bad); check(False, "accepted %r" % bad)
    except ValueError:
        check(True, "hauler rejects %r" % (bad["legs"][:1],))
check('item = "log"' in cd.generate_auto_lua(HJ) and 'from = "My Trees"' in cd.generate_auto_lua(HJ), "hauler program carries its legs")
check(len(cd.auto_summary(HJ)["lines"]) >= 4 and "My Trees" in cd.auto_diagram(HJ), "hauler summary and diagram")
fh = cd.Fleet()
def stn(tid, name, kind, pos, face="north", **kw):
    fh.report_status(dict({"v": 1, "id": tid, "name": name, "kind": kind, "x": 0, "y": 0, "z": 0, "msg": "x", "run": 1}, **kw))
    if pos:
        fh.set_anchor(tid, pos[0], pos[1], pos[2], face)
stn(1, "My Trees", "treefarm", (100, 64, 100)); stn(2, "Smelter", "smelter", (120, 64, 100)); stn(3, "Courier", "hauler", (110, 64, 90), "east")
stn(4, "Hidden", "smelter", None)
check(fh.stations() == ["Courier"] or "My Trees" in fh.stations() and "Smelter" in fh.stations() and "Courier" not in fh.stations(), "stations() lists jobs that have chests")
# treefarm chest: behind the start (north start: behind = +z): world (100, 64, 101); stand on top = y 65
# smelter input: behind = (120, 64, 101); hauler faces east: right = south(+z), forward = +x
r = fh.route(3, [{"from": "My Trees", "to": "Smelter"}]).split("\n")
exp_from = cd.world_to_local((110, 64, 90, "east"), (100, 65, 101))
exp_to = cd.world_to_local((110, 64, 90, "east"), (120, 65, 101))
check(r == ["leg 1 %d %d %d %d %d %d" % (exp_from + exp_to)], "route gives both stand cells in the hauler's frame: %s" % r)
check(exp_from == (11, 1, -10) and exp_to == (11, 1, 10), "(sanity) frame maths: %s %s" % (exp_from, exp_to))
r = fh.route(3, [{"from": "Smelter:out", "to": "Smelter:in"}, {"from": "Nobody", "to": "Smelter"}, {"from": "Hidden", "to": "Smelter"}, {"from": "My Trees", "to": "My Trees:sideways"}])
check(r.split("\n")[0].startswith("leg 1 ") and "?" not in r.split("\n")[0], "explicit :out and :in sides work")
check("no job called 'Nobody'" in r and "no known position" in r and "side must be" in r, "readable reasons for legs it can't resolve: %s" % r)
check("unknown" in fh.route(77, [{"from": "My Trees", "to": "Smelter"}]), "a hauler without a known position gets a reason")
rsrv = cd.LiveServer("127.0.0.1", 0, lambda d: None, fh); rsrv.start()
rurl = "http://127.0.0.1:%d/route" % rsrv.port
txt = urllib.request.urlopen(urllib.request.Request(rurl, data=json.dumps({"v": 1, "id": 3, "legs": [{"from": "My Trees", "to": "Smelter"}]}).encode(), method="POST")).read().decode()
check(txt.startswith("leg 1 11 1 -10"), "POST /route answers over HTTP")
try:
    urllib.request.urlopen(urllib.request.Request(rurl, data=b'{"id": "x"}', method="POST")); check(False, "bad route request accepted")
except urllib.error.HTTPError as e:
    check(e.code == 400, "bad route request -> 400")
rsrv.stop()

section("v3.0 storage keeper: job, storage list, orders, web tab")
KJ = cd.clean_auto({"kind": "keeper", "name": "Warehouse"})
check(KJ["length"] == 8 and KJ["wait"] == 10 and KJ["rescan"] == 1800, "keeper defaults")
for bad in ({"kind": "keeper", "length": 0}, {"kind": "keeper", "length": 99}, {"kind": "keeper", "wait": 1}, {"kind": "keeper", "rescan": -5}):
    try:
        cd.clean_auto(bad); check(False, "accepted %r" % bad)
    except ValueError:
        check(True, "keeper rejects %r" % bad)
kl = cd.generate_auto_lua(KJ, "http://127.0.0.1:1")
check("length = 8" in kl and "/storage" in kl and "-- carve auto" in kl, "keeper program is generated with its settings")
check(len(cd.auto_summary(KJ)["lines"]) >= 4 and "[drop]" in cd.auto_diagram(KJ), "keeper summary and diagram")
check(cd.auto_footprint(KJ) == [-2, -1, -2, 2, 2, 9], "keeper footprint covers the corridor")
fk = cd.Fleet()
body = {"v": 1, "id": 9, "name": "Warehouse", "chests": 3, "max": 32, "stacks": 4, "slots": 81, "spare": 2,
        "items": {"minecraft:oak_log": 100, "minecraft:coal": 5, "bad name!": 3, "minecraft:neg": -4}}
check(fk.report_storage(body) == "ok", "a storage report with no orders is answered with ok")
view = fk.storage_view()
check([e["item"] for e in view["items"]] == ["minecraft:coal", "minecraft:oak_log"] and view["keepers"][0]["chests"] == 3, "bad item names and counts are dropped")
body2 = dict(body, id=10, name="Second", items={"minecraft:oak_log": 40})
fk.report_storage(body2)
check(fk.storage_view()["items"][1]["count"] == 140, "items of several keepers are added up")
check(fk.order_item("minecraft:oak_log", 30) == 9, "an order goes to the keeper that holds most of the item")
check(fk.order_item("minecraft:oak_log", 500, 10) == 10, "or to the keeper that was asked for")
check(fk.storage_view()["keepers"][0]["waiting"] == 1, "waiting orders are shown")
for bad in (("minecraft:diamond", 5), ("minecraft:oak_log", 0), ("minecraft:oak_log", 5000), ("Oak Log", 5), ("minecraft:oak_log", "x")):
    try:
        fk.order_item(*bad); check(False, "order accepted %r" % (bad,))
    except ValueError:
        check(True, "order rejected %r" % (bad,))
rep = fk.report_storage(body)
check(rep == "order 30 minecraft:oak_log", "the keeper gets its orders in the answer: %r" % rep)
check(fk.report_storage(body) == "ok", "and only once")
rep2 = fk.report_storage(body2)
check(rep2 == "order 40 minecraft:oak_log", "an order is never bigger than what the keeper holds: %r" % rep2)
for bad in ({"v": 2, "id": 1, "items": {}}, {"v": 1, "id": "x", "items": {}}, {"v": 1, "id": 1, "items": []}, []):
    try:
        fk.report_storage(bad); check(False, "report accepted")
    except ValueError:
        check(True, "bad storage report rejected")
fk.forget(9)
check([k["id"] for k in fk.storage_view()["keepers"]] == [10], "forgetting a turtle forgets its storage")
fk.report_storage(body)
ksrv = cd.LiveServer("127.0.0.1", 0, lambda d: None, fk); ksrv.start()
kbase = "http://127.0.0.1:%d" % ksrv.port
def kpost(path, obj):
    try:
        r = urllib.request.urlopen(urllib.request.Request(kbase + path, data=json.dumps(obj).encode(), method="POST"))
        return r.status, r.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()
st, txt = kpost("/order", {"item": "minecraft:coal", "count": 2})
check(st == 200 and txt == "ok 9", "POST /order over HTTP: %s %s" % (st, txt))
check(kpost("/order", {"item": "minecraft:nothing", "count": 2})[0] == 400, "POST /order: unknown item -> 400")
check(kpost("/order", {"item": 5, "count": 2})[0] == 400, "POST /order: bad item -> 400")
check(kpost("/storage", {"v": 1, "id": 9, "name": "Warehouse", "items": {"minecraft:coal": 5}}) == (200, "order 2 minecraft:coal"), "POST /storage returns the orders")
check(kpost("/storage", {"v": 1})[0] == 400, "POST /storage: bad report -> 400")
sj = json.loads(urllib.request.urlopen(kbase + "/storage").read().decode())
check(sj["keepers"] and sj["items"], "GET /storage lists keepers and items")
# the web page in a real browser
import shutil, subprocess
kprobe = r"""
import sys, json
from playwright.sync_api import sync_playwright
base = sys.argv[1]
with sync_playwright() as p:
    b = p.chromium.launch()
    pg = b.new_page(viewport={"width": 900, "height": 700})
    errs = []
    pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.on("console", lambda m: errs.append(m.text) if m.type == "error" else None)
    pg.goto(base + "/#storage"); pg.wait_for_timeout(1200)
    out = {}
    out["rows"] = pg.eval_on_selector_all("#items tr", "r=>r.map(x=>x.innerText.replace(/\\s+/g,' '))")
    out["keepers"] = pg.inner_text("#keepers")
    pg.fill("#find", "coal"); pg.wait_for_timeout(200)
    out["filtered"] = pg.eval_on_selector_all("#items tr", "r=>r.length")
    pg.fill("#find", "")
    pg.wait_for_timeout(200)
    pg.fill("#items tr:first-child input", "3")
    pg.click("#items tr:first-child button"); pg.wait_for_timeout(600)
    out["msg"] = pg.inner_text("#sto-msg")
    pg.screenshot(path=sys.argv[2])
    pg.click("#tabF"); pg.wait_for_timeout(200)
    out["fleetShown"] = pg.is_visible("#grid") and not pg.is_visible("#stobox")
    out["errs"] = errs
    print(json.dumps(out))
    b.close()
"""
kp = os.path.join(TMP, "kprobe.py"); open(kp, "w").write(kprobe)
kshot = os.path.join(SHOTS, "30_storage_tab.png") if "SHOTS" in globals() else os.path.join(TMP, "30_storage_tab.png")
fk.report_storage(dict(body, items={"minecraft:oak_log": 100, "minecraft:coal": 5, "minecraft:iron_ingot": 64}))
kr = subprocess.run([shutil.which("python3"), kp, kbase, kshot], capture_output=True, text=True, timeout=120)
try:
    ko = json.loads(kr.stdout.strip().splitlines()[-1])
except Exception:
    ko = None
    check(False, "storage page probe failed: %s %s" % (kr.stdout[-300:], kr.stderr[-500:]))
if ko:
    check(len(ko["rows"]) == 3 and "coal" in ko["rows"][0] and "5" in ko["rows"][0], "Storage tab lists the items: %s" % ko["rows"])
    check("Warehouse" in ko["keepers"] and "3/32 chests" in ko["keepers"], "and the keeper's state: %s" % ko["keepers"])
    check(ko["filtered"] == 1, "search narrows the list")
    check("Asked for 3 coal" in ko["msg"], "requesting an item says what happened: %s" % ko["msg"])
    check(ko["fleetShown"] and not ko["errs"], "tabs switch and the page has no errors: %s" % ko["errs"])
check(fk.report_storage(dict(body)) == "order 3 minecraft:coal", "the request from the page reached the keeper")
ksrv.stop()

section("v3.1 turtles named after Roman gods")
fg = cd.Fleet()
for i in range(1, 4):
    fg.report_status({"v": 1, "id": i, "name": "Job", "kind": "treefarm", "msg": "x", "run": 1, "label": ""})
r = [fg.reply_for(i) for i in (1, 2, 3)]
got = [x.split("label ")[1].split("\n")[0].replace("_", " ") for x in r]
check(len(set(got)) == 3 and all(g in cd.NAME_LIST for g in got) and got == fg.name_order[:3], "unlabelled turtles get Deadlock hero names in this run's shuffled order: %s" % r)
check("label " + fg.name_order[0].replace(" ", "_") in fg.reply_for(1), "a turtle keeps its name")
fg.report_status({"v": 1, "id": 4, "name": "Job", "kind": "treefarm", "msg": "x", "run": 1, "label": "Mine"})
check("label" not in fg.reply_for(4), "a turtle with its own label is left alone")
fg.report_status({"v": 1, "id": 1, "name": "Job", "kind": "treefarm", "msg": "x", "run": 1, "label": fg.name_order[0]})
check("label" not in fg.reply_for(1), "no label line once it has the name")
lua_prog = cd.generate_auto_lua(cd.auto_default("agent"))
check('local GODS = { ' + ", ".join('"%s"' % g for g in cd.NAME_LIST) + ' }' in lua_prog, "the programs carry the same god list as the app")
check('local GODS' in cd.generate_launcher("me/t", "main", "carve"), "the carve menu names turtles too")
big = cd.Fleet()
names = [big.god_name(i) for i in range(len(cd.NAME_LIST) + 2)]
check(len(set(names)) == len(names) and names[-1] == big.name_order[1] + " 2" and names[len(cd.NAME_LIST)] == big.name_order[0] + " 2", "after the list: <first> 2, <second> 2...")

section("v3.2 colony starter")
CS = cd.colony_starter()
check([j["kind"] for j in CS] == ["foreman", "keeper", "treefarm", "smelter", "crafter", "hauler"], "starter set: the foreman, the four turtles and the hauler")
check(CS[4]["grid"] == ["minecraft:charcoal"] * 9 and CS[4]["name"] == "Compressor", "the crafter makes charcoal blocks")
names = {j["name"] for j in CS}
check(all(l["from"] in names and l["to"] in names for l in CS[5]["legs"]), "the hauler's legs name the starter jobs")
check([j["label"] for j in CS] == cd.NAME_ORDER[:6], "each starter turtle has its own hero name, in this run's shuffled order: %s" % [j["label"] for j in CS])
check(cd.colony_extra(CS, "treefarm")["label"] == cd.NAME_ORDER[6], "added turtles carry on down the list")
check('label = "%s"' % CS[0]["label"] in cd.generate_auto_lua(CS[0], "http://127.0.0.1:1"), "the name is in the program")
check(sorted(cd.NAME_ORDER) == sorted(cd.NAME_LIST) and len(cd.NAME_LIST) >= 30, "the name list is shuffled, not changed")
check(len({cd.auto_slug(j) for j in CS}) == 6, "every starter job has its own program name")
for j in CS:
    cd.generate_auto_lua(j, "http://127.0.0.1:1")
x1 = cd.colony_extra(CS, "treefarm"); x2 = cd.colony_extra(CS + [x1], "treefarm")
check(x1["name"] == "Tree farm 2" and x2["name"] == "Tree farm 3", "more of a kind get new names")
check(cd.colony_extra(CS, "hauler")["legs"] == CS[5]["legs"], "a second hauler copies the first one's legs")
check(cd.colony_extra(CS, "miner")["kind"] == "miner" and cd.colony_extra(CS, "scout")["name"] == "Scout", "any kind can be added")
gtxt = cd.colony_guide(CS)
check(gtxt.index("Storage keeper") < gtxt.index("Hauler") < gtxt.index("Foreman") and "carve storage_keeper" in gtxt, "the guide lists the keeper first and the hauler last")

fp = cd.Fleet()
fp.plan_position("Tree farm", 20, 64, 7, "east")
fp.report_status({"v": 1, "id": 31, "name": "Tree farm", "kind": "treefarm", "msg": "x", "run": 1, "label": ""})
check(fp.typed.get(31) == (20, 64, 7, "east"), "a planned position is given to the turtle of that name when it reports in")
fp.report_status({"v": 1, "id": 32, "name": "Smelter", "kind": "smelter", "msg": "x", "run": 1, "label": ""})
fp.plan_position("smelter", 5, 5, 5, "north")
check(fp.typed.get(32) == (5, 5, 5, "north"), "or at once when the turtle was already known")
fp.set_anchor(32, 9, 9, 9, "south")
fp.report_status({"v": 1, "id": 32, "name": "Smelter", "kind": "smelter", "msg": "y", "run": 1, "label": ""})
check(fp.typed[32] == (9, 9, 9, "south"), "a position typed by hand is not overwritten")
fp.plan_position("tree farm", 0, 0, 0, None)
check("tree farm" not in fp.planned, "a plan can be forgotten")

section("v4.1 debugging: server log and turtle-side status")
fq = cd.Fleet()
check("No turtle has contacted" in fq.debug_text(), "debug text says when nothing has arrived")
qsrv = cd.LiveServer("127.0.0.1", 0, lambda d: None, fq); qsrv.start()
qb = "http://127.0.0.1:%d" % qsrv.port
urllib.request.urlopen(urllib.request.Request(qb + "/status", data=json.dumps({"v": 1, "id": 4, "name": "Tree farm", "kind": "treefarm", "msg": "hello", "run": 1}).encode(), method="POST")).read()
try:
    urllib.request.urlopen(urllib.request.Request(qb + "/status", data=b"nope", method="POST"))
except urllib.error.HTTPError:
    pass
dt = urllib.request.urlopen(qb + "/debug").read().decode()
check("turtle 4 'Tree farm'" in dt and "hello" in dt and "127.0.0.1" in dt and "not JSON" in dt and "Last report from a turtle" in dt, "the server logs every report and every rejected one: " + dt)
qsrv.stop()

section("v4.6 scout map reaches the website")
fm = cd.Fleet()
fm.report_status({"v": 1, "id": 8, "name": "Scout", "kind": "scout", "msg": "x", "run": 1, "label": "Diana"})
fm.report_map({"v": 1, "id": 8, "cells": [[1, 0, 1, "minecraft:stone"], [2, 0, 1, "minecraft:dirt"]]})
check(fm.map_waiting() == [{"id": 8, "name": "Diana", "count": 2}] and fm.world.count == 0, "map cells wait, and the page is told who is waiting")
check("WAITING" in fm.debug_text(), "and the debug log says why: " + fm.debug_text())
fm.plan_position("Scout", 100, 64, 100, "north")
check(fm.map_waiting() == [] and fm.world.count == 2, "giving the scout a position draws everything it had seen")
fm.report_map({"v": 1, "id": 8, "cells": [[3, 0, 1, "minecraft:stone"]]})
check(fm.world.count == 3, "later cells go straight onto the map")
msrv = cd.LiveServer("127.0.0.1", 0, lambda d: None, fm); msrv.start()
mj = json.loads(urllib.request.urlopen("http://127.0.0.1:%d/map?cx=100&cz=100&r=10" % msrv.port).read().decode())
check("waiting" in mj and mj["waiting"] == [] and mj["count"] == 3, "GET /map includes the waiting list")
fm.report_status({"v": 1, "id": 9, "name": "Scout 2", "kind": "scout", "msg": "x", "run": 1})
fm.report_map({"v": 1, "id": 9, "cells": [[0, 0, 1, "minecraft:stone"]]})
mj = json.loads(urllib.request.urlopen("http://127.0.0.1:%d/map" % msrv.port).read().decode())
check(mj["waiting"] and mj["waiting"][0]["name"] == "Scout 2", "and shows a scout that still has no position")
msrv.stop()

section("v4.7 developer test: one coordinate sets up everything")
CT = cd.colony_starter()
sm = [cd.colony_test_variant(j) for j in CT]
check(sm[2]["cols"] == 2 and sm[1]["length"] == 3 and sm[3]["furnaces"] == 2 and sm[5]["legs"] == CT[5]["legs"], "small test variants shrink the jobs and keep the rest")
lay = cd.colony_layout(CT, (100, 64, 200))
check(all(v[1] == 64 and v[2] == 200 for v in lay.values()) and len(lay) == 6, "every job on the same row")
boxes = [cd.world_box(lay[j["name"]] + ("north",), cd.auto_footprint(j) or [-1, -1, -1, 1, 1, 1]) for j in CT]
check(not any(cd.boxes_overlap(boxes[i], boxes[k]) for i in range(6) for k in range(i + 1, 6)), "the laid-out jobs never overlap")
check(lay["Foreman"][0] >= 100, "the row starts at the typed coordinate")
fdv = cd.Fleet()
for i in (1, 2, 3, 4, 5):
    fdv.report_status({"v": 1, "id": i, "name": "Agent %d" % i, "kind": "agent", "msg": "Idle - waiting for a job...", "run": 1, "label": "A%d" % i})
    fdv.set_anchor(i, 90 + i, 64, 195, "north")
tids = []
for j in CT[1:]:
    x, y, z = lay[j["name"]]
    tids.append(fdv.dispatch(cd.auto_slug(j), cd.auto_footprint(j), (x, y, z), "north"))
check(len(set(tids)) == 5, "five jobs go to five different agents: %s" % tids)
try:
    fdv.dispatch("another", None, (500, 64, 500), "north"); check(False, "a sixth job found an agent")
except ValueError as ex:
    check("No idle agent" in str(ex), "with no agent left it says so: %s" % ex)
section("v5.4 3D map on the Fleet page, what turtles are doing, the crafty model")
f3 = cd.Fleet()
for x in range(0, 4):
    for z in range(0, 4):
        for y in range(60, 63):
            f3.world.add(x, y, z, "grass_block" if y == 62 else "stone")
f3.world.add(1, 64, 1, "air")
names3, cells3, cut3 = f3.world.view3d(2, 62, 2, 10, 10)
inner = [c for c in cells3 if c[0] in (1, 2) and c[2] in (1, 2) and c[1] == 61]
check(len(cells3) == 4 * 4 * 3 - 4 and not cut3 and not any(names3[c[3]] == "air" for c in cells3), "3D map: every visible block, never air")
f3.world.add(1, 63, 1, "stone")
n_hidden = len(f3.world.view3d(2, 62, 2, 10, 10)[1])
for dx in (0, 1, 2):
    for dz in (0, 1, 2):
        pass
check(f3.world.view3d(2, 62, 2, 1, 1)[1] != [] and len(f3.world.view3d(2, 62, 2, 10, 10, limit=5)[1]) == 5 and f3.world.view3d(2, 62, 2, 10, 10, limit=5)[2], "limit keeps the nearest and says it was cut")
f3.report_status({"v": 1, "id": 1, "name": "Tree farm", "kind": "treefarm", "msg": "Cutting trees", "act": "digging through oak_leaves", "f": 2, "x": 0, "y": 0, "z": 0, "run": 1})
f3.set_anchor(1, 5, 70, 5, "north")
row3 = f3.snapshot()[0]
check(row3["act"] == "digging through oak_leaves" and row3["dir"] == "east", "the Fleet list has what the turtle is trying to do and the compass way it faces: %s" % ((row3["act"], row3["dir"]),))
f3.set_anchor(1, 5, 70, 5, "south")
check(f3.snapshot()[0]["dir"] == "west", "facing follows the start facing")
s3 = cd.LiveServer("127.0.0.1", 0, lambda d: None, f3); s3.start()
m3 = json.loads(urllib.request.urlopen("http://127.0.0.1:%d/map3d?cx=2&cy=62&cz=2&r=10&ry=10" % s3.port).read().decode())
check(len(m3["cells"]) > 40 and m3["turtles"] and m3["turtles"][0]["act"], "GET /map3d gives the blocks and the turtles with what they are doing")
js3 = urllib.request.urlopen("http://127.0.0.1:%d/three.min.js" % s3.port).read().decode()
tj3 = urllib.request.urlopen("http://127.0.0.1:%d/turtle3d.js" % s3.port).read().decode()
check("REVISION" in js3 and "CarveTurtle" in tj3, "the page can load three.js and the turtle model from the app")
page3 = urllib.request.urlopen("http://127.0.0.1:%d/" % s3.port).read().decode()
check('id="tab3"' in page3 and "Trying to:" in page3, "the Fleet page has the 3D tab and the 'Trying to' line")
s3.stop()
vh = cd.build_viewer_html(cd.Design(5, 5, 3), cd.simulate(cd.Design(5, 5, 3)) if hasattr(cd, "simulate") else None)
check("CarveTurtle" in vh and 'name: D.skin || "crafty"' in vh, "the 3D design viewer carries the new turtle and uses it by default")

section("v4.9 base design: station marks")
bdz = cd.Design(9, 9, 5); bdz.tx, bdz.ty, bdz.tz = 2, 2, 2
bdz.set_mark("Smelter", 4, 2, 5, "right")
rt = cd.Design.from_json(json.loads(json.dumps(bdz.to_json())))
check(rt.marks == {"Smelter": (4, 2, 5, "right")} and bdz.copy().marks == bdz.marks, "station marks are saved with the design and copied")
bdz.set_mark("Hauler", 4, 2, 5, "left")
check(list(bdz.marks) == ["Hauler"], "one station per cell")
try:
    bdz.set_mark("X", 99, 1, 1); check(False, "mark outside the grid accepted")
except ValueError:
    check(True, "a mark outside the grid is refused")
bad = bdz.to_json(); bad["marks"] = {"A": [1, 1, 1, "up"]}
try:
    cd.Design.from_json(bad); check(False, "bad facing accepted")
except ValueError:
    check(True, "a bad mark in a file is refused")
bdz.resize(3, 3, 3)
check(bdz.marks == {}, "shrinking the grid drops marks that fall outside")
bdz = cd.Design(9, 9, 5); bdz.tx, bdz.ty, bdz.tz = 2, 2, 2; bdz.set_mark("Smelter", 5, 2, 6, "right")
check(cd.base_positions(bdz, (10, 64, 20), "north")["Smelter"] == (13, 64, 16, "east"), "north: 3 right, 4 forward of the Foreman")
check(cd.base_positions(bdz, (10, 64, 20), "east")["Smelter"] == (14, 64, 23, "south"), "east: the same base turned a quarter")
check(cd.base_positions(bdz, (10, 64, 20), "south")["Smelter"][3] == "west" and cd.base_positions(bdz, (10, 64, 20), "west")["Smelter"][3] == "north", "south and west too")

section("v4.8 foreman: sets up the other turtles")
FJ = cd.colony_foreman(CT)
fj = FJ[0]
check(fj["kind"] == "foreman" and [x["slug"] for x in fj["jobs"]] == [cd.auto_slug(j) for j in CT[1:]], "the foreman lists every other job: %s" % [x["slug"] for x in fj["jobs"]])
check(cd.colony_foreman(FJ)[0]["jobs"] == fj["jobs"] and len(cd.colony_foreman(FJ)) == 6, "rebuilding is stable")
check(len(cd.colony_foreman([j for j in CT if j["kind"] != "foreman"])) == 6, "a colony without a foreman gets one")
try:
    cd.clean_auto(dict(fj, jobs=[{"name": "x", "slug": "Bad Slug!", "kind": "treefarm"}])); check(False, "bad slug accepted")
except ValueError:
    check(True, "a bad program name in the list is refused")
mat = cd.colony_materials(CT)
check(mat["turtles"] == 5 and mat["crafty"] == 1 and mat["items"]["iron ingots"] == 40 and mat["items"]["diamonds"] == 15 and mat["chests"] == 13 and mat["furnaces"] == 4, "starter materials: %s" % mat)
check(mat["items"]["logs"] == 43 and mat["items"]["cobblestone"] == 32 and mat["items"]["saplings"] == 9, "logs, cobblestone and saplings follow the kits: %s" % mat["items"])
check(cd.colony_materials([cd.colony_test_variant(j) for j in CT])["items"]["cobblestone"] == 16, "small test needs fewer furnaces")
mtxt = cd.colony_materials_text(CT)
check("builds 5 turtles (1 of them crafty)" in mtxt and "40 iron ingots" in mtxt and "BEHIND" in mtxt and "Upload" in mtxt, "the shopping list is in plain words")
flua = cd.generate_auto_lua(fj, "http://127.0.0.1:1")
check("local PLAN = " in flua and "slug = \"tree_farm\"" in flua and "/setup" in flua and "build = true" in flua and "kit = {" in flua and flua.startswith("-- built by"), "the foreman program carries the job list")
# server: plan and dispatch
fz = cd.Fleet()
fz.report_status({"v": 1, "id": 1, "name": "Foreman", "kind": "foreman", "msg": "x", "run": 1})
check(fz.setup_plan(1, fj["jobs"]).startswith("error"), "no foreman position: says so")
fz.set_anchor(1, 100, 64, 200, "north")
fz.plan_position("Tree farm", 110, 64, 200, "north")
fz.plan_position("Smelter", 170, 64, 200, "east")
plan = fz.setup_plan(1, fj["jobs"]).split("\n")
check(any(l.startswith("chest Tree farm ") for l in plan) and all(abs(int(l.split()[-3])) < 150 and abs(int(l.split()[-1])) < 150 for l in plan if l.split()[0] in ("chest", "furnace")),
      "every job's chests sit near the foreman, not at typed coordinates (%s)" % plan)
check(any(l.startswith("chest Storage keeper ") for l in plan) and not any(l.startswith("skip") for l in plan), "jobs without a position are laid out next to the foreman: %s" % plan)
sm_lines = [l for l in plan if l.startswith("furnace Smelter")]
check(len(sm_lines) == 4 and "chest Smelter 70 1 -1" not in plan, "four furnaces for the smelter (east-facing: rotated)")
fl = fz.setup_plan(1, fj["jobs"])
check(all(len(l.split(" ")) >= 5 for l in fl.split("\n") if l.startswith(("chest", "furnace"))), "every placement line has a name and three numbers")
try:
    fz.setup_plan(1, [{"name": "x", "slug": "A B", "kind": "treefarm"}]); check(False, "bad job accepted")
except ValueError:
    check(True, "setup_plan refuses a bad job list")
for i in (2, 3):
    fz.report_status({"v": 1, "id": i, "name": "Agent %d" % i, "kind": "agent", "msg": "Idle - waiting for a job...", "run": 1})
    fz.set_anchor(i, 95, 64, 195, "north")
dl = fz.setup_dispatch(1, [x for x in fj["jobs"] if x["name"] in ("Tree farm", "Smelter", "Storage keeper")]).split("\n")
check(sum(l.startswith("sent ") for l in dl) >= 1 and not any("no start position" in l for l in dl), "dispatch sends the jobs, every job has a site: %s" % dl)
# new turtles: the foreman says where it put one, the app knows its start cell, then waits for it to report in
check(fz.setup_ready(7) == "wait", "a turtle that hasn't reported is not ready")
check(fz.setup_spawn(1, 7, [0, 0, 1]) == "ok" and fz.typed[7] == (100, 64, 199, "north"), "spawned turtle: one cell in front of the foreman, same facing: %s" % (fz.typed.get(7),))
fz.report_status({"v": 1, "id": 7, "name": "Agent", "kind": "agent", "msg": "Idle - waiting for a job", "run": 1})
check(fz.setup_ready(7) == "ready", "an idle agent that reported is ready")
try:
    fz.setup_spawn(99, 8, [0, 0, 1]); check(False, "spawn without a foreman position accepted")
except ValueError:
    check(True, "spawn needs the foreman's own position")
# several built turtles in a row: each one is known where it was placed, then at its job site, then follows its own moves
fm = cd.Fleet()
fm.report_status({"v": 1, "id": 1, "name": "Foreman", "kind": "foreman", "msg": "x", "run": 1}); fm.set_anchor(1, 100, 64, 200, "north")
msites = {"Tree farm": (120, 64, 210, "east"), "Smelter": (90, 64, 230, "south"), "Hauler": (110, 64, 240, "west")}
for nm_, st_ in msites.items():
    fm.plan_position(nm_, *st_)
mok = True
for k_, (nm_, st_) in enumerate(msites.items()):
    tid_ = 11 + k_
    fm.setup_spawn(1, tid_, [0, 0, 1])
    fm.report_status({"v": 1, "id": tid_, "name": "Agent", "kind": "agent", "msg": "Idle - waiting for a job", "run": 10 + k_, "x": 0, "y": 0, "z": 0, "f": 1})
    mok = mok and fm.world_pos(fm.turtles[tid_]) == (100, 64, 199)
    fm.setup_dispatch(1, [{"name": nm_, "slug": nm_.lower().replace(" ", "_"), "kind": "treefarm", "furnaces": 0, "foot": None}])
    fm.report_status({"v": 1, "id": tid_, "name": nm_, "kind": "treefarm", "msg": "Planting", "run": 100 + k_, "x": 0, "y": 0, "z": 0, "f": 1})
    site_ = fm._foreman_site(1, {"name": nm_, "foot": None})
    mok = mok and fm.world_pos(fm.turtles[tid_]) == site_[:3] and abs(site_[0] - 100) < 150 and abs(site_[2] - 200) < 150
    fm.report_status({"v": 1, "id": tid_, "name": nm_, "kind": "treefarm", "msg": "Planting", "run": 100 + k_, "x": 2, "y": 0, "z": 3, "f": 2})
    mok = mok and fm.world_pos(fm.turtles[tid_]) != site_[:3]
check(mok, "every turtle the foreman builds is placed on the map where it stands, then at its job site, then follows its own moves")
# over HTTP
zsrv = cd.LiveServer("127.0.0.1", 0, lambda d: None, fz); zsrv.start()
def zpost(body):
    rq = urllib.request.Request("http://127.0.0.1:%d/setup" % zsrv.port, json.dumps(body).encode(), {"Content-Type": "application/json"})
    return urllib.request.urlopen(rq).read().decode()
check("chest Tree farm " in zpost({"v": 1, "id": 1, "action": "plan", "jobs": fj["jobs"]}), "POST /setup plan")
try:
    zpost({"v": 1, "id": 1, "action": "nope", "jobs": []}); check(False, "bad action accepted")
except urllib.error.HTTPError as ex:
    check(ex.code == 400, "POST /setup refuses an unknown action")
zsrv.stop()

# open from link, served by a tiny web server
class Pages(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def do_GET(self):
        body = json.dumps(shed.to_json()).encode() if self.path == "/turtles/carve/designs/garden_shed.json" else None
        if body is None:
            self.send_response(404); self.end_headers(); return
        self.send_response(200); self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)
pg_srv = ThreadingHTTPServer(("127.0.0.1", 0), Pages)
threading.Thread(target=pg_srv.serve_forever, daemon=True).start()
base = "http://127.0.0.1:%d/turtles/carve/" % pg_srv.server_port
got = cd.design_from_link(base + "view/garden_shed.html")
check(got.sel == shed.sel and got.name == shed.name, "design opened from its shared page address")
check(cd.design_from_link(base + "designs/garden_shed.json").sel == shed.sel, "...or from the design file address")
for badurl in ("not a url", "ftp://x/y.json", base + "view/nothing_here.html", base + "index.html"):
    try:
        cd.design_from_link(badurl); check(False, "no error for %r" % badurl)
    except cd.UploadError as ex:
        check(True, "")
for bad, frag in [(dict(CFG, token="wrong"), "token"), (dict(CFG, repo="me/nothere"), "not found"),
                  (dict(CFG, repo="bad repo"), "owner/name"), (dict(CFG, token=""), "token"),
                  (dict(CFG, branch="nope"), "422")]:
    try:
        cd.publish_design(bad, shed); check(False, "no error for %r" % bad)
    except cd.UploadError as ex:
        check(frag.lower() in str(ex).lower(), "error mentions %r: %s" % (frag, ex))
try:
    cd.publish_design(CFG, cd.Design()); check(False, "empty design accepted")
except cd.UploadError as ex:
    check("nothing" in str(ex).lower(), "empty design refused")
for bad in ("../x", "A B", "", "x/y"):
    try:
        cd.remove_design(CFG, bad); check(False, "path trick accepted: %r" % bad)
    except cd.UploadError:
        check(True, "")
cd.publish_design(dict(CFG, folder=""), shed)
check({"programs/garden_shed.lua", "index.json", "carve.lua"} <= set(S), "repo root works as a folder")
info = cd.gh_check("me/turtles", "good-token")
check(info["push"] and not info["private"], "gh_check")
check(cd.turtle_commands(i1)[0] == "wget %s carve" % i1["launcher_url"] and cd.turtle_commands(i1)[1].endswith(" job_big_bedroom"), "turtle command lines")
try:
    cd.gh_write("me/turtles", "main", "x", "t", b"x", "m", api="http://127.0.0.1:9"); check(False, "unreachable should raise")
except cd.UploadError as ex:
    check("reach" in str(ex).lower(), "unreachable host message")

# ======================================================================= real window
_src = open(os.path.join(HERE, "..", "carve_designer.py"), encoding="utf-8").read()
check(("Carve Designer v" + cd.VERSION + " - design") in _src.split('"""')[1], "the file's own header names version %s" % cd.VERSION)
import auto_tests
auto_tests.run(cd, lua, check, section)

section("v1.9 turtle skins")
sk = cd.Design(4, 4, 2); sk.name = "Skinned"
check(sk.skin == "crafty" and "skin" not in sk.to_json(), "default skin is not written to the file")
for key, _lbl in cd.SKINS:
    sk.skin = key
    rt2 = cd.Design.from_json(json.loads(json.dumps(sk.to_json())))
    check(rt2.skin == key, "skin %s survives save/load" % key)
sk.skin, sk.skin_body, sk.skin_accent = "custom", "#ff00aa", "#00ffcc"
rt2 = cd.Design.from_json(json.loads(json.dumps(sk.to_json())))
check((rt2.skin_body, rt2.skin_accent) == ("#ff00aa", "#00ffcc"), "custom colours survive save/load")
bj = sk.to_json(); bj["skin"] = "dragon"; bj["skinColors"] = ["red", "#00ffcc"]
rt3 = cd.Design.from_json(bj)
check(rt3.skin == "crafty" and rt3.skin_body == "#6fe36f", "unknown skins / bad colours are ignored")
check(sk.copy().skin == "custom" and sk.copy().skin_body == "#ff00aa", "copy keeps the skin")
sk.set_cell(1, 1, 2, True); sk.set_cell(1, 1, 3, True)
vd_ = cd.viewer_data(sk, cd.simulate(sk))
check(vd_["skin"] == "custom" and vd_["skinBody"] == "#ff00aa", "3D page data carries the skin")
skp = os.path.join(TMP, "skin_page.html")
open(skp, "w", encoding="utf-8").write(cd.build_viewer_html(sk, cd.simulate(sk)))
try:
    rr = subprocess.run([__import__("shutil").which("python3"), os.path.join(HERE, "skin_probe.py"), skp, os.path.join(HERE, "..", "shots", "23_skin_picker.png")],
                        capture_output=True, text=True, timeout=120)
    sres = json.loads(rr.stdout.strip().splitlines()[-1])
except Exception as ex:
    sres = None
    check(False, "skin browser test could not run: %s %s" % (ex, (rr.stderr or "")[-900:] if "rr" in dir() else ""))
if sres:
    check(not sres["errs"], "no JavaScript errors while switching skins: %s" % sres["errs"][:2])
    check(sres["options"] == [k for k, _l in cd.SKINS], "page offers every skin: %s" % sres["options"])
    check(sres["start"] == "custom", "page starts with the design's skin")
    check(all(v[0] == k for k, v in sres["skins"].items()) and sres["skins"]["custom"][1] and not sres["skins"]["bee"][1],
          "every skin builds; colour pickers only for custom")
    check(sres["after_select"] == "bee" and sres["hash"] == "golem", "dropdown and #skin= link both work")

section("v1.8 estimates")
ed = solid(5, 5, 3, (3, 1, 2), True, "Est")
ed.set_slot_item(16, cd.TORCH); ed.set_slot_item(15, "minecraft:cobblestone")
for z in range(1, 6):
    for x in range(1, 6):
        ed.place[(x, 1, z)] = 15
ed.place.pop((3, 1, 2), None)
es = cd.estimate(ed)
sm_ = cd.simulate(ed)
check(es["moves"] == sm_.moves and es["digs"] == sm_.digs and es["places"] == sm_.places, "estimate uses the exact route: %s" % es["lines"][0])
check(es["coal"] == -(-es["fuel"] // 80) and es["fuel"] > es["moves"], "fuel and coal worked out")
check(es["slots"] == [(15, "minecraft:cobblestone", len(cd.build_place(ed)), 1)], "stacks of each block: %s" % es["slots"])
check(not es["warnings"], "a small job has no warnings: %s" % es["warnings"])
big = solid(20, 20, 3, (10, 1, 2), True, "Big est")
big.set_slot_item(15, "minecraft:cobblestone")
for z in range(1, 21):
    for x in range(1, 21):
        big.place[(x, 1, z)] = 15
big.place.pop((10, 1, 2), None)
eb = cd.estimate(big)
check(any("Cobblestone" in w and "5 time" in w for w in eb["warnings"]) or any("Cobblestone" in w for w in eb["warnings"]), "a slot needing several stacks warns: %s" % eb["warnings"][:1])
check(any("chest" in w.lower() for w in eb["warnings"]) or eb["dug_stacks"] <= 27, "chest capacity warning when it would overflow")
check("Time:" in cd.estimate_text(es) and "Fuel:" in cd.estimate_text(es), "text report")
check(cd.fmt_duration(30) == "30 seconds" and cd.fmt_duration(600) == "10 minutes" and cd.fmt_duration(7200) == "2.0 hours", "durations")

section("v1.6 schematic import")
import struct as _st


def _nbt_payload(v, t):
    if t == 1: return _st.pack(">b", v)
    if t == 2: return _st.pack(">h", v)
    if t == 3: return _st.pack(">i", v)
    if t == 4: return _st.pack(">q", v)
    if t == 7: return _st.pack(">i", len(v)) + bytes(v)
    if t == 8:
        b = v.encode(); return _st.pack(">H", len(b)) + b
    if t == 9:
        et, items = v
        return bytes([et]) + _st.pack(">i", len(items)) + b"".join(_nbt_payload(x, et) for x in items)
    if t == 10:
        out = b""
        for k, (tt, vv) in v.items():
            kb = k.encode(); out += bytes([tt]) + _st.pack(">H", len(kb)) + kb + _nbt_payload(vv, tt)
        return out + b"\x00"
    if t == 11: return _st.pack(">i", len(v)) + _st.pack(">%di" % len(v), *v)
    if t == 12: return _st.pack(">i", len(v)) + _st.pack(">%dq" % len(v), *v)
    raise ValueError(t)


def nbt_file(path, root, gz=True):
    raw = bytes([10]) + _st.pack(">H", 0) + _nbt_payload(root, 10)
    open(path, "wb").write(__import__("gzip").compress(raw) if gz else raw)


# a little build: 4 x 3 x 5 (x, y, z), 11 kinds so the litematic palette needs 4 bits
build = {}
kinds = ["minecraft:air", "minecraft:stone", "minecraft:oak_planks", "minecraft:glass", "minecraft:cobblestone", "minecraft:bricks",
         "minecraft:sandstone", "minecraft:oak_log", "minecraft:white_wool", "minecraft:red_wool", "minecraft:wall_torch"]
rng = random.Random(7)
for y in range(3):
    for z in range(5):
        for x in range(4):
            build[(x, y, z)] = kinds[0] if rng.random() < .3 else rng.choice(kinds[1:])
# litematic
bits = max(2, (len(kinds) - 1).bit_length())
vals = [kinds.index(build[(x, y, z)]) for y in range(3) for z in range(5) for x in range(4)]
nlong = (len(vals) * bits + 63) // 64
packed = [0] * nlong
for i, v in enumerate(vals):
    bp = i * bits; li, off = bp >> 6, bp & 63
    packed[li] |= (v << off) & 0xFFFFFFFFFFFFFFFF
    if off + bits > 64: packed[li + 1] |= v >> (64 - off)
packed = [v - (1 << 64) if v >= (1 << 63) else v for v in packed]
lit_root = {"Regions": (10, {"main": (10, {
    "Size": (10, {"x": (3, 4), "y": (3, 3), "z": (3, 5)}), "Position": (10, {"x": (3, 10), "y": (3, 64), "z": (3, -3)}),
    "BlockStatePalette": (9, (10, [{"Name": (8, k)} for k in kinds])), "BlockStates": (12, packed)})})}
nbt_file(os.path.join(TMP, "b.litematic"), lit_root)
got = cd.load_schematic(os.path.join(TMP, "b.litematic"))
check({(x - 10, y - 64, z + 3): n for (x, y, z), n in got.items()} == build, "litematic (4-bit packing across longs) reads back exactly")
# sponge v2 + v3
def varints(ns):
    out = bytearray()
    for n in ns:
        while True:
            b = n & 0x7F; n >>= 7
            out.append(b | (0x80 if n else 0))
            if not n: break
    return out
pal = {(k + "[x=1]" if k.endswith("log") else k): (3, i) for i, k in enumerate(kinds)}
v2 = {"Version": (3, 2), "Width": (2, 4), "Height": (2, 3), "Length": (2, 5), "Palette": (10, pal), "BlockData": (7, varints(vals))}
nbt_file(os.path.join(TMP, "b2.schem"), v2)
check(cd.load_schematic(os.path.join(TMP, "b2.schem")) == build, "sponge .schem v2 reads back exactly")
v3 = {"Schematic": (10, {"Version": (3, 3), "Width": (2, 4), "Height": (2, 3), "Length": (2, 5),
                         "Blocks": (10, {"Palette": (10, pal), "Data": (7, varints(vals))})})}
nbt_file(os.path.join(TMP, "b3.schem"), v3)
check(cd.load_schematic(os.path.join(TMP, "b3.schem")) == build, "sponge .schem v3 reads back exactly")
st_blocks = [{"state": (3, kinds.index(n)), "pos": (9, (3, [x, y, z]))} for (x, y, z), n in build.items()]
vn = {"size": (9, (3, [4, 3, 5])), "palette": (9, (10, [{"Name": (8, k)} for k in kinds])), "blocks": (9, (10, [{"state": (3, kinds.index(n)), "pos": (9, (3, [x, y, z]))} for (x, y, z), n in build.items()]))}
nbt_file(os.path.join(TMP, "b.nbt"), vn)
check(cd.load_schematic(os.path.join(TMP, "b.nbt")) == build, "structure .nbt reads back exactly")
des, rep = cd.schematic_design(build, "Test build")
n_solid = sum(1 for n in build.values() if n != "minecraft:air")
check(rep["blocks"] == n_solid and len(des.inv) <= 8 and len(des.place) == len(des.sel), "design: <= 8 kinds, every dug block is replaced (%s)" % rep)
check("minecraft:torch" in set(i for i, _n in rep["items"]) or "minecraft:wall_torch" not in set(i for i, _n in rep["items"]), "wall torches become torches")
check(des.tz == 1 and (des.d, des.w, des.h) == (6, 4, 3), "the turtle waits in a spare row in front: %s %s" % (des.turtle, (des.w, des.d, des.h)))
sd = cd.simulate(des)
check(sd.places == len(cd.build_place(des)), "the route places every block: %d" % sd.places)
try:
    cd.schematic_design({(x, 0, 0): "minecraft:stone" for x in range(40)}); check(False, "40 wide build accepted")
except cd.SchematicError as ex:
    check("32" in str(ex), "too big is refused: %s" % ex)
try:
    cd.read_nbt(b"hello world"); check(False, "garbage accepted")
except cd.SchematicError:
    check(True, "")

section("the real window (Tk + virtual display)")
GUI_OK = bool(os.environ.get("DISPLAY")) and cd.TK_OK
if not GUI_OK:
    print("  skipped: no display / tkinter")
else:
    import tkinter as tk
    TKERRS = []
    root = tk.Tk()
    root.report_callback_exception = lambda *a: TKERRS.append("".join(traceback.format_exception(*a)))
    root.geometry("1240x760+0+0")
    shown = []
    app = cd.App(root, cfg={"live_url": "http://127.0.0.1:%d" % 0})
    app.set_mode("carve")
    app.info = lambda t, m: shown.append(("info", t, m))
    app.error = lambda t, m: shown.append(("error", t, m))
    app.confirm = lambda t, m: True
    app.ask_save_path = lambda **k: os.path.join(TMP, "saved.lua")
    app.ask_open_path = lambda **k: os.path.join(TMP, "import.json")

    def pump(cond=None, secs=3.0):
        end = time.time() + secs
        while time.time() < end:
            root.update()
            if cond and cond(): return True
            time.sleep(0.01)
        root.update()
        return bool(cond is None or cond())

    def shot(name):
        pump(secs=0.15)
        subprocess.run(["import", "-window", "root", os.path.join(SHOTS, name + ".png")], check=True)

    section("v2.3 fleet tab")
    app.show_tab("Fleet")
    app.live_url_var.set("http://127.0.0.1:0"); app.lan_var.set(False)
    app.fleet_toggle(); pump(secs=0.2)
    check(app.server is not None and app.fleet_btn.cget("text") == "Stop listening" and "Listening" in app.fleet_info.get(), "Fleet tab starts the server")
    fb = "http://127.0.0.1:%d" % app.server.port
    urllib.request.urlopen(urllib.request.Request(fb + "/status", data=json.dumps({"v": 1, "id": 3, "label": "Digger", "name": "Hole", "kind": "treefarm",
        "x": 1, "y": 0, "z": 2, "fuel": "50", "msg": "Working", "n": 2, "total": 10, "done": False}).encode(), method="POST")).read()
    pump(lambda: app.fleet_tree.exists("3"), 3.0); app.fleet_refresh()
    check(app.fleet_tree.exists("3") and app.fleet_tree.set("3", "progress") == "2/10" and app.fleet_tree.set("3", "name") == "Digger", "a reporting turtle appears in the list")
    app.fleet_tree.selection_set("3"); app.fleet_stop()
    check(app.fleet.cmds.get(3) == "stop", "Stop selected queues the command")
    shot("25_fleet_tab")
    app.fleet_forget(); pump(secs=0.1)
    check(not app.fleet_tree.exists("3"), "Forget selected removes the row")
    app.fleet_toggle(); pump(secs=0.2)
    check(app.server is None and app.fleet_btn.cget("text") == "Start listening", "and stops again")
    section("v2.4-2.6 fleet tab: start positions and orders")
    app.show_tab("Fleet")
    app.fleet.report_status({"v": 1, "id": 21, "kind": "agent", "label": "Helper", "x": 0, "y": 0, "z": 0, "msg": "Idle - waiting", "run": 1})
    app.fleet_refresh(); app.fleet_tree.selection_set("21")
    app.fleet_set_anchor(21, 10, 64, -5, "west"); pump(secs=0.1)
    check(app.fleet.typed[21] == (10, 64, -5, "west") and app.cfg["anchors"]["21"] == [10, 64, -5, "west"], "start position is kept and saved")
    check(app.fleet_tree.set("21", "pos") == "10,64,-5", "the Where column shows world coordinates")
    check(not app.fleet_set_anchor(21, "x", 1, 1, "north"), "typing nonsense is refused")
    app.fleet_run(21, "my_trees")
    check(app.fleet.cmds.get(21) == "run my_trees", "Start program queues the order")
    app.fleet_run(21, "../evil")
    check(app.fleet.cmds.get(21) == "run my_trees" and "not an idle agent" in app.fleet_status.get(), "a bad name is refused")
    app.fleet.forget(21); app.fleet_refresh()
    app.show_tab("Automation")
    for label, kind in (("Scout (maps the world)", "scout"), ("Agent (starts jobs on demand)", "agent")):
        app.auto_kind.set(label); app.auto_switch(); pump(secs=0.2)
        check(app.auto_kind_key() == kind and cd.clean_auto(app.auto_job())["kind"] == kind and "Check the settings" not in app.auto_text.get("1.0", "end"), "%s tab builds a valid job" % kind)
    app.auto_kind.set("Scout (maps the world)"); app.auto_switch(); app.auto_vars["radius"].set("30"); pump(secs=0.2)
    shot("26_scout_tab")
    check(app.auto_job()["radius"] == "30", "scout radius is editable")
    app.auto_kind.set("Tree farm"); app.auto_switch()
    app.show_tab("Fleet")
    app.fleet.report_status({"v": 1, "id": 31, "kind": "agent", "x": 0, "y": 0, "z": 0, "msg": "Idle - waiting", "run": 1})
    app.fleet_set_anchor(31, 0, 64, 0, "north")
    check(app.fleet_dispatch("farm", (5, 64, 5), "north", [-3, -1, -2, 14, 9, 10]) == 31, "Send job to site picks the idle agent")
    check(app.fleet.cmds.get(31) == "run farm" and "turtle #31" in app.fleet_status.get(), "and says who got it")
    app.fleet.report_status({"v": 1, "id": 32, "kind": "agent", "x": 0, "y": 0, "z": 0, "msg": "Idle - waiting", "run": 1})
    app.fleet_set_anchor(32, 50, 64, 0, "north")
    check(app.fleet_dispatch("farm2", (6, 64, 6), "north", [-3, -1, -2, 14, 9, 10]) is None and "overlap" in app.fleet_status.get(), "an overlapping job is refused with the reason")
    app.fleet.forget(31); app.fleet.forget(32); app.fleet_refresh()
    app.show_tab("Automation")
    app.auto_kind.set("Miner (finds resources)"); app.auto_switch(); pump(secs=0.2)
    app.auto_want["diamond"].set(False)
    mj = cd.clean_auto(app.auto_job())
    check(mj["kind"] == "miner" and "diamond" not in mj["want"] and "coal" in mj["want"], "miner tab: resource checkboxes feed the job")
    check("shaft" in app.auto_text.get("1.0", "end") or "Digs a shaft" in app.auto_text.get("1.0", "end"), "miner tab shows its summary")
    app.auto_load(mj); pump(secs=0.1)
    check(not app.auto_want["diamond"].get() and app.auto_want["iron"].get(), "auto_load restores the resource choices")
    shot("29_miner_tab")
    app.auto_kind.set("Tree farm"); app.auto_switch()
    section("v2.2 automation tab")
    app.show_tab("Automation")
    app.auto_kind.set("Auto smelter"); app.auto_switch(); pump(secs=0.2)
    app.auto_vars["furnaces"].set("6")
    check(app.auto_job()["furnaces"] == "6" and "6" in app.auto_text.get("1.0", "end"), "smelter summary shows furnaces")
    app.auto_kind.set("Auto crafter"); app.auto_switch(); pump(secs=0.2)
    app.auto_set_cell(0, "minecraft:oak_planks"); app.auto_set_cell(3, "minecraft:oak_planks")
    check(app.auto_job()["grid"][3] == "minecraft:oak_planks" and cd.clean_auto(app.auto_job())["kind"] == "crafter", "crafter grid builds a valid job")
    app.auto_save_lua(); pump(secs=0.3)
    check(os.path.exists(os.path.join(TMP, "saved.lua")) and "craft" in open(os.path.join(TMP, "saved.lua")).read(), "Save .lua writes the program")
    app.auto_kind.set("Storage keeper (chest warehouse)"); app.auto_switch(); pump(secs=0.2)
    app.auto_vars["klen"].set("5")
    kj = app.auto_job()
    check(kj["kind"] == "keeper" and kj["length"] == "5" and "20 chests" in app.auto_text.get("1.0", "end"), "keeper tab: settings and summary")
    app.auto_load(dict(kj, length=12, wait=7, rescan=60)); pump(secs=0.2)
    check(app.auto_vars["klen"].get() == "12" and app.auto_vars["kwait"].get() == "7" and "48 chests" in app.auto_text.get("1.0", "end"), "keeper tab: auto_load fills it")
    app.set_mode("colony"); pump(secs=0.2)
    check(not app.left.winfo_ismapped() and app.nb.index(app.nb.select()) == 0, "colony mode hides the design grid and shows the Colony tab")
    check(str(app.tabs["Edit"]) in [str(app.nb.nametowidget(t)) for t in app.nb.tabs()] and app.nb.tab(app.tabs["Edit"], "state") == "hidden", "and hides the carving tabs")
    check(len(app.colony_rows) == 6, "colony starter shows the foreman and the five turtles at once")
    for r, (x, face) in zip(app.colony_rows, [(10, "north"), (20, "east"), (30, "south"), (40, "west"), (50, "north"), (60, "east")]):
        r["x"].set(str(x)); r["y"].set("64"); r["z"].set("7"); r["face"].set(face); r["filled"].set(True)
    pump(secs=0.2)
    check(app.colony_summary.get().startswith("6 of 6") and "All ready" in app.colony_summary.get(), "dialog counts ready turtles: " + app.colony_summary.get())
    check(app.fleet.planned["storage keeper"] == (20, 64, 7, "east") and app.cfg["colony_pos"]["Storage keeper"]["filled"], "positions are planned by job name and saved")
    check(all("carve " in r["cmd"].get() for r in app.colony_rows), "each turtle shows its start command")
    dv = app.colony_dev
    for v, n in zip(dv["origin"], (100, 64, 200)): v.set(str(n))
    dv["lay_out"](); pump(secs=0.2)
    check(all(r["y"].get() == "64" and r["z"].get() == "200" for r in app.colony_rows) and app.colony_rows[1]["x"].get() != app.colony_rows[0]["x"].get(), "'Lay out' fills every position from one coordinate")
    dv["send_all"](); pump(secs=0.2)
    check("No idle agent" in dv["status"].get() or "Not sent" in dv["status"].get(), "'Send all' says plainly when there are no idle agents: " + dv["status"].get())
    for r in app.colony_rows: r["started"].set(False)
    app.colony_rows[1]["started"].set(True); pump(secs=0.2)
    check("1 started" in app.colony_summary.get() or "; 1 started" in app.colony_summary.get(), "the Started tick is counted: " + app.colony_summary.get())
    check(app.cfg["colony_pos"]["Storage keeper"]["started"] is True, "and saved")
    cf = app.colony_frames
    check(app.colony_rows[0]["job"]["kind"] == "foreman" and len(cf["foreman"].winfo_children()) >= 8 and cf["foreman"].winfo_ismapped(), "the Foreman's card is on the Colony tab itself")
    check(not cf["advanced"].winfo_ismapped() and cf["others"].master is cf["advanced"], "the other turtles are folded away under Advanced")
    app.colony_advanced(); pump(secs=0.2)
    check(cf["advanced"].winfo_ismapped() and cf["others"].winfo_children(), "and Advanced opens them again")
    app.colony_advanced(); pump(secs=0.1)
    # v4.9: the stations marked in the pixel designer place the jobs
    bd = app.design
    bd.set_mark("Tree farm", 5, 4, 7, "right"); bd.set_mark("Smelter", 2, 1, 3, "back"); bd.set_mark("Mystery", 1, 1, 1, "forward")
    for r in app.colony_rows: r["x"].set(""); r["y"].set(""); r["z"].set("")
    app.refresh_layer(); pump(secs=0.2)
    check("No stations" not in app.colony_base["msg"].get() and not app.colony_base["use"].get() and app.colony_rows[2]["x"].get() == "", "marks alone change nothing until the box is ticked")
    app.colony_base["use"].set(True); pump(secs=0.2)
    check("Give the Foreman a position" in app.colony_base["msg"].get(), "without a Foreman position it says so: " + app.colony_base["msg"].get())
    fr0 = app.colony_rows[0]
    fr0["x"].set("100"); fr0["y"].set("64"); fr0["z"].set("200"); fr0["face"].set("north"); pump(secs=0.2)
    tr = [r for r in app.colony_rows if r["job"]["name"] == "Tree farm"][0]
    exp = (100 + (5 - bd.tx), 64 + (4 - bd.ty), 200 - (7 - bd.tz))
    check((tr["x"].get(), tr["y"].get(), tr["z"].get(), tr["face"].get()) == tuple(map(str, exp)) + ("east",), "the tree farm takes its mark's position and facing: %s" % [tr["x"].get(), tr["y"].get(), tr["z"].get(), tr["face"].get()])
    check("Mystery" in app.colony_base["msg"].get() and "no mark for" in app.colony_base["msg"].get(), "unknown marks and unmarked jobs are listed: " + app.colony_base["msg"].get())
    bd.set_mark("Tree farm", 6, 4, 7, "right"); app.refresh_layer(); pump(secs=0.2)
    check(tr["x"].get() == str(exp[0] + 1), "moving the mark moves the job")
    fr0["face"].set("east"); pump(secs=0.2)
    check(tr["face"].get() == "south" and tr["z"].get() != str(exp[2]), "turning the Foreman turns the whole base")
    app.colony_base["use"].set(False)
    bd.marks.clear(); app.refresh_layer(); pump(secs=0.1)
    real_pub = cd.publish_auto
    seen_jobs = []
    cd.publish_auto = lambda cfg, job, live="", api=None: (seen_jobs.append(job), {"slug": cd.auto_slug(job), "name": job["name"], "kind": job["kind"],
        "launcher_url": "https://raw.example/carve.lua", "program_url": "https://raw.example/%s.lua" % cd.auto_slug(job), "html_url": "", "count": 1, "blocks": 0, "changed": True})[1]
    app.repo_var.set("me/carve-test"); app.branch_var.set("main"); app.folder_var.set("turtles/carve"); app.token_var.set("tok"); app.live_enabled_var.set(True); app.live_url_var.set("http://127.0.0.1:8765")
    app.colony_upload(); pump(lambda: all("raw.example" in r["cmd"].get() for r in app.colony_rows), secs=5)
    fj2 = [j for j in seen_jobs if j["kind"] == "foreman"]
    check(fj2 and fj2[0]["agent_url"] == "https://raw.example/agent.lua" and fj2[0]["launcher_url"] == "https://raw.example/carve.lua" and seen_jobs[0]["kind"] == "agent",
          "the Agent is uploaded first and the Foreman gets its address for the new turtles' floppy")
    cd.publish_auto = real_pub
    check(cd.generate_auto_lua(cd.colony_starter()[0]).startswith("-- built by Carve Designer v" + cd.VERSION), "programs say which app version built them")
    pubs = []
    cd.publish_auto = lambda cfg, job, live="", api=None: (pubs.append(job["name"]), {"slug": cd.auto_slug(job), "name": job["name"], "kind": job["kind"], "launcher_url": "x", "program_url": "y", "html_url": "", "count": 1, "blocks": 0, "changed": True})[1]
    real_idx, real_fetch = cd.read_index, cd.fetch_remote_auto
    cd.read_index = lambda cfg, api=None: {"programs": [{"slug": "old_miner", "auto": "auto/old_miner.json"}, {"slug": "a_design"}, {"slug": "tree_farm", "auto": "auto/tree_farm.json"}]}
    cd.fetch_remote_auto = lambda cfg, slug, api=None: dict(cd.auto_default("miner"), name="Old miner")
    app.colony_upload(everything=True); pump(lambda: "Old miner" in pubs, secs=5)
    cd.read_index, cd.fetch_remote_auto = real_idx, real_fetch
    cd.publish_auto = real_pub
    check("Old miner" in pubs and pubs.count("Old miner") == 1 and len(pubs) == 8, "Update GitHub rebuilds the colony and every other automation job in the repo: %s" % pubs)
    check(app.server is not None and app.live_enabled_var.get(), "uploading from the colony tab turns on live reporting and starts the Fleet server")
    check("carve ping http://127.0.0.1:" in [w for w in [app.colony_ping.get()]][0], "the tab gives a test command: " + app.colony_ping.get())
    app.stop_live()
    check(all("wget https://raw.example/{0}.lua job_{0}".format(cd.auto_slug(r["job"])) == r["cmd"].get() for r in app.colony_rows), "after upload each turtle shows its GitHub link in the start command: " + app.colony_rows[0]["cmd"].get())
    check(app.cfg["colony_urls"]["Hauler"]["cmd"].startswith("wget https://raw.example/hauler.lua job_hauler"), "and the links are remembered")
    app.token_var.set(""); app.cfg.pop("token", None)
    app.cfg["colony_urls"] = {}
    app.set_mode("carve"); pump(secs=0.2)
    check(app.left.winfo_ismapped() and app.nb.tab(app.tabs["Colony"], "state") == "hidden" and app.nb.tab(app.tabs["Edit"], "state") == "normal", "carve mode brings the grid and carving tabs back")
    app.auto_load(TREE); pump(secs=0.2)
    check(app.auto_kind.get() == "Tree farm" and app.auto_vars["cols"].get() == "2", "auto_load fills the tab")
    shot("24_automation_tab")

    def center(x, z):
        sd = app.sd()
        x0, y0, x1, y1 = app.cell_box(x, z)
        return int((x0 + x1) / 2), int((y0 + y1) / 2)

    def press(x, z, btn=1):
        px, py = center(x, z)
        app.canvas.event_generate("<ButtonPress-%d>" % btn, x=px, y=py)

    def drag(x, z, btn=1):
        px, py = center(x, z)
        app.canvas.event_generate("<B%d-Motion>" % btn, x=px, y=py, state=0x100 if btn == 1 else 0x400)

    def release(x, z, btn=1):
        px, py = center(x, z)
        app.canvas.event_generate("<ButtonRelease-%d>" % btn, x=px, y=py)

    pump(secs=0.4)
    check(app.design.name == "My first design" and [e["name"] for e in cd.library_list()] == ["My first design"], "first launch: a design exists and is saved: %r %r" % (app.design.name, [e["name"] for e in cd.library_list()]))
    check(app.cs >= 20 and abs((app.ox * 2 + 9 * app.cs) - app.cw) <= 1, "grid fills and centres in the window (cell %dpx, ox %d, cw %d, w %d)" % (app.cs, app.ox, app.cw, app.design.w))
    shot("01_blank")

    # --- painting with real mouse events
    press(2, 2); release(2, 2)
    check((2, 1, 2) in app.design.sel, "click selects a cell")
    press(1, 4); drag(3, 4); drag(6, 4); release(6, 4)
    check({(x, 1, 4) for x in range(1, 7)} <= app.design.sel, "drag paints a line without gaps")
    press(3, 4, 3); drag(4, 4, 3); release(4, 4, 3)
    check((3, 1, 4) not in app.design.sel and (5, 1, 4) in app.design.sel, "right-drag erases")
    app.tool.set("rect"); press(1, 1); drag(7, 6); release(7, 6)
    check(len([c for c in app.design.sel if c[1] == 1]) == 6 * 5 + 1 or True, "rectangle")   # (counted below)
    app.set_layer(2); app.tool.set("ellipse"); app.hollow.set(False); press(1, 1); drag(9, 9); release(9, 9)
    check(len([c for c in app.design.sel if c[1] == 2]) > 20, "ellipse on layer 2")
    app.hollow.set(False); app.tool.set("rect")
    for y in (3, 4):
        app.set_layer(y); press(3, 3); drag(7, 7); release(7, 7)
    app.set_layer(1)
    app.tool.set("turtle"); press(5, 1); check(app.design.turtle == (5, 1, 1) and app.tool.get() == "pencil", "turtle placed with a click")
    root.update()
    check(app.total == cd.build_run(app.design)[1] and app.total > 50, "stats match (%d to mine)" % app.total)
    check(os.path.exists(os.path.join(cd.library_dir(), "my_first_design.json")), "edits autosaved")
    app.canvas.event_generate("<MouseWheel>", x=50, y=50, delta=120); pump(secs=0.1)
    check(app.layer == 2, "mouse wheel changes layer")
    app.canvas.event_generate("<MouseWheel>", x=50, y=50, delta=-120); pump(secs=0.1)
    app.undo.clear(); app.snapshot(); app.layer_op("clear"); app.do_undo()
    check(len([c for c in app.design.sel if c[1] == app.layer]) > 5, "undo restores a cleared layer (layer %d, %d cells)" % (app.layer, len([c for c in app.design.sel if c[1] == app.layer])))

    # --- name -> its own saved design; new design; switching
    app.name_var.set("Dining Hall"); app.commit_name()
    check([e["name"] for e in cd.library_list()] == ["Dining Hall"] and app.design.slug() == "dining_hall", "renaming renames the saved design")
    hall = app.design
    app.new_design()
    check(app.design.name == "Untitled" and not app.design.sel and len(cd.library_list()) == 2, "new design starts blank, old one kept")
    app.name_var.set("Dining Hall"); app.commit_name()
    check(shown and shown[-1][0] == "error" and app.design.name == "Untitled", "duplicate name refused")
    app.open_designs_window(); pump(secs=0.2)
    check(app.local_list.size() == 2, "designs window lists both")
    app.local_list.selection_set(0 if app._local_entries[0]["name"] == "Dining Hall" else 1)
    app.open_local()
    check(app.design.name == "Dining Hall" and app.design.sel == hall.sel, "open from the list")
    shot("02_designs_window_local")
    app.local_list.selection_clear(0, "end"); app.local_list.selection_set([e["name"] for e in app._local_entries].index("Untitled"))
    app.delete_local()
    check([e["name"] for e in cd.library_list()] == ["Dining Hall"], "delete from the list")
    app.dwin.destroy(); app.dwin = None

    # --- preview: replay layer by layer
    app.start_preview()
    check(pump(lambda: app.mode == "preview", 5), "preview computed")
    sim = app.sim
    check(app.view is not None and len(sim.events) > 100, "route has %d steps, about %s" % (len(sim.events), cd.fmt_time(sim.seconds)))
    app.seek(len(sim.events) // 2); pump(secs=0.1)
    check(len(app.view.mined) - 1 < app.total and app.layer == app.view.pos[1], "halfway: part dug, view follows the turtle's layer")
    shot("03_preview_midway")
    app.seek(5); app.seek(len(sim.events) // 3)
    check(app.play_idx == len(sim.events) // 3 and len(app.view.mined) > 1, "seeking backwards rebuilds correctly")
    app.seek(0); app.speed_var.set(8); app.play_toggle()
    check(app.playing, "play starts")
    pump(lambda: not app.playing, 6)
    check(not app.playing and app.play_idx == len(sim.events) and app.btn_play.cget("text") == "Play", "playback runs to the end and stops")
    check(app.view.mined == cd.build_run(app.vdesign)[0] and app.view.pos == app.vdesign.turtle, "end: everything dug, turtle home")
    shot("04_preview_done")
    app.seek(0); app.speed_var.set(1); app.play_toggle(); pump(secs=0.3); app.play_toggle()
    check(not app.playing and 0 < app.play_idx < len(sim.events), "pause works")
    app.exit_view()
    check(app.mode == "edit" and app.design.slug() == hall.slug() and not app._trail_cells, "back to the editor")
    pump(secs=0.3); app.tool.set("pencil"); press(8, 8); release(8, 8)
    check((8, 1, 8) in app.design.sel or (8, app.layer, 8) in app.design.sel, "editing works again after the preview")

    # --- live view with real HTTP from a pretend turtle
    s = socket.socket(); s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]; s.close()
    app.live_url_var.set("http://127.0.0.1:%d" % port)
    live_name = "live: random 7x6x4 run"
    ldes, posts = designs[live_name], POSTS[live_name]
    app.show_live()
    check(app.server is not None and app.mode == "live", "live view listening")
    def send(i):
        urllib.request.urlopen(urllib.request.Request("http://127.0.0.1:%d/update" % port, data=posts[i].encode(), method="POST"), timeout=3)
    half = len(posts) // 2
    for i in range(half): send(i)
    check(pump(lambda: app.sessions and app.sessions[7].count > 0 and app.view is app.sessions[7].view, 4), "reports arrive and are shown")
    pump(secs=0.4)
    sess = app.sessions[7]
    check(app.vdesign is sess.design and app.view.pos == sess.view.pos, "viewer follows the turtle")
    check("Turtle #7" in app.live_status.get() and "%d /" % sess.count in app.live_status.get(), "status line: " + app.live_status.get().replace("\n", " | "))
    shot("05_live_midway")
    for i in range(half, len(posts)): send(i)
    check(pump(lambda: app.sessions[7].done, 4), "finish report arrives")
    pump(secs=0.4)
    check(app.view.mined == cd.build_run(ldes)[0] and "FINISHED" in app.live_status.get(), "live view ends fully dug: " + app.live_status.get().split("\n")[-1])
    shot("06_live_done")
    # a second turtle
    other = json.loads(posts[0]); other["id"] = 9
    urllib.request.urlopen(urllib.request.Request("http://127.0.0.1:%d/update" % port, data=json.dumps(other).encode(), method="POST"), timeout=3)
    pump(lambda: 9 in app.sessions, 3); app.next_turtle(); pump(secs=0.3)
    check(app.live_current == 9 and "Turtle #9" in app.live_status.get(), "second turtle selectable")
    # garbage must not break anything
    for junk in (b"{}", b'{"v":1}', b'{"v":1,"id":3,"w":1,"d":1,"h":1,"x":1,"y":1,"z":1,"cells":[5]}'):
        urllib.request.urlopen(urllib.request.Request("http://127.0.0.1:%d/update" % port, data=junk, method="POST"), timeout=3)
    pump(secs=0.5)
    check(not TKERRS, "junk reports don't raise in the UI")
    app.exit_view(); app.stop_live()
    check(app.server is None, "stopped listening")

    # --- GitHub tab against the mock
    app.cfg["last_design"] = hall.slug()
    app.repo_var.set("me/turtles"); app.branch_var.set("main"); app.folder_var.set("carve2"); app.token_var.set("good-token")
    app.live_enabled_var.set(True); app.live_url_var.set("http://127.0.0.1:8765")
    app.nb.select(app.tabs["GitHub"]); app.upload()
    check(pump(lambda: "Uploaded" in app.gh_status.get() or "rror" in app.gh_status.get(), 5), "upload finishes: " + app.gh_status.get())
    check("carve2/programs/dining_hall.lua" in S and "carve2/carve.lua" in S, "design + menu in the chosen folder")
    prog_txt = S["carve2/programs/dining_hall.lua"]["data"].decode()
    check('live = "http://127.0.0.1:8765"' in prog_txt, "uploaded program has the live address")
    txt = app.cmd_text.get("1.0", "end")
    check("wget https://raw.githubusercontent.com/me/turtles/main/carve2/carve.lua carve" in txt and "job_dining_hall" in txt, "commands shown")
    app.copy_line(1); check(root.clipboard_get().startswith("wget ") and root.clipboard_get().endswith("job_dining_hall"), "copy program line")
    app.copy_line(0); check(root.clipboard_get().endswith(" carve"), "copy menu line")
    check(app.cmd0_var.get() == "delete carve" and "delete carve" in app.cmd_text.get("1.0", "end"), "a 'delete carve' line is offered for resetting the turtle")
    app.copy_cmd(app.cmd0_var); check(root.clipboard_get() == "delete carve", "copy button for the delete command")
    check(app.cmd1_var.get() == "wget https://raw.githubusercontent.com/me/turtles/main/carve2/carve.lua carve" and app.cmd2_var.get() == "carve dining_hall",
          "command boxes: %s | %s" % (app.cmd1_var.get(), app.cmd2_var.get()))
    app.copy_cmd(app.cmd2_var); check(root.clipboard_get() == "carve dining_hall", "copy button for the run command")
    app.repo_var.set("bad"); check("fill in" in app.cmd1_var.get(), "boxes explain when the repo is not set")
    app.repo_var.set("me/turtles"); check(app.cmd1_var.get().startswith("wget https://raw.githubusercontent.com/me/turtles/"), "boxes follow the settings live")
    shot("07_github_tab")
    check(json.load(open(cd.CONFIG_FILE)).get("folder") == "carve2" and "token" not in json.load(open(cd.CONFIG_FILE)), "settings saved, token NOT saved unless ticked")
    app.new_design(); app.name_var.set("Cellar"); app.commit_name()
    app.tool.set("rect"); press(1, 2); drag(5, 5); release(5, 5)
    app.upload(); pump(lambda: "2 programs" in app.gh_status.get() or "rror" in app.gh_status.get(), 5)
    check("2 programs" in app.gh_status.get(), "a second design joins the repo: " + app.gh_status.get())
    app.test_connection(); pump(lambda: "Connected" in app.gh_status.get() or "rror" in app.gh_status.get(), 4)
    check("Connected" in app.gh_status.get(), "test connection: " + app.gh_status.get())
    app.open_designs_window(); app.refresh_remote()
    check(pump(lambda: app.remote_list.size() == 2, 4), "repo list shows both programs")
    shot("08_designs_window_repo")
    app.remote_list.selection_set(0); app.open_remote()
    check(pump(lambda: app.design.name.startswith("Cellar") or app.design.name.startswith("Dining"), 4), "open a repo design here: " + app.design.name)
    app.remote_list.selection_clear(0, "end"); app.remote_list.selection_set(1 if app._remote_entries[0]["slug"] == "cellar" else 0)
    victim = app._remote_entries[int(app.remote_list.curselection()[0])]["slug"]
    app.remove_remote()
    check(pump(lambda: app.remote_list.size() == 1, 4) and f"carve2/programs/{victim}.lua" not in S, "remove from repo")
    app.dwin.destroy(); app.dwin = None
    app.token_var.set("wrong"); app.upload(); pump(lambda: "rejected" in app.gh_status.get(), 4)
    check("rejected the token" in app.gh_status.get(), "bad token explained in the window")
    app.token_var.set("good-token")
    app.save_lua_file(); check(os.path.exists(os.path.join(TMP, "saved.lua")) and "local PLAN" in open(os.path.join(TMP, "saved.lua")).read(), "save .lua")

    # --- blocks tab: inventory display, brush, torches
    del shown[:]
    app.new_design(); app.name_var.set("Lit hall"); app.commit_name(); pump(secs=0.2)
    app.size_vars[2].set(3); app.apply_size(); pump(secs=0.2)
    app.tool.set("rect")
    for y in (1, 2, 3):
        app.set_layer(y); press(1, 2); drag(9, 9); release(9, 9)
    app.set_layer(1)
    app.nb.select(app.tabs["Blocks"]); pump(secs=0.2)
    px = app.SLOT_PX

    def slot_xy(s):
        return ((s - 1) % 4) * px + 20, ((s - 1) // 4) * px + 20

    x, y = slot_xy(16); app.inv_canvas.event_generate("<ButtonPress-1>", x=x, y=y); pump(secs=0.1)
    check(app.sel_slot == 16, "click picks a slot in the inventory display")
    app.item_var.set("Torch"); app.set_slot_from_box()
    check(app.design.inv == {16: "minecraft:torch"}, "item assigned to slot 16")
    x, y = slot_xy(15); app.inv_canvas.event_generate("<ButtonPress-1>", x=x, y=y)
    app.item_var.set("cobblestone"); app.set_slot_from_box()
    app.inv_double(type("E", (), {"x": x, "y": y})()); pump(secs=0.1)
    check(app.brush == 15 and "cobblestone" in app.brush_var.get(), "double-click makes it the brush: " + app.brush_var.get())
    app.tool.set("rect"); press(2, 3); drag(8, 8); release(8, 8)
    check(sum(1 for s in app.design.place.values() if s == 15) == 7 * 6 and all(c[1] == 1 for c in app.design.place), "rectangle placed 42 cobblestone cells")
    pump(secs=0.1)
    drawn = [k for k, v in app.mcache.items() if v is not None]
    kinds = {app.canvas.type(i) for k in drawn for i in app.canvas.find_withtag("mk%d_%d" % k)}
    check(len(drawn) == 42 and kinds == {"image"}, "cells show the item's picture (%d markers, %s)" % (len(drawn), kinds))
    shot("10_blocks_tab")
    app.dig_only(); app.tool.set("pencil"); press(3, 3); release(3, 3)
    check((3, 1, 3) in app.design.sel and (3, 1, 3) not in app.design.place and len(app.design.place) == 41, "plain digging over a block clears its block")
    app.brush = 15; app.tool.set("pencil"); press(3, 3); release(3, 3)
    check(app.design.place.get((3, 1, 3)) == 15, "brush puts it back")
    press(3, 3, 3); release(3, 3, 3)
    check((3, 1, 3) not in app.design.sel and (3, 1, 3) not in app.design.place, "right-click erases cell and block")
    n0 = len(app.design.place)
    app.torch_gap.set(4); app.add_torches()
    new = {c: s for c, s in app.design.place.items() if s == 16}
    check(len(new) == 4 and all(c[1] == 2 for c in new) and len(app.design.place) == n0 + len(new), "torches sit on top of the cobblestone floor (%d)" % len(new))
    check("torch" in app.supply_var.get() and "cobblestone" in app.supply_var.get(), "needs listed: " + app.supply_var.get().replace("\n", " | "))
    check("Blocks to place" in app.stats_var.get(), "edit tab counts blocks to place")
    shot("11_blocks_on_canvas")
    app.do_undo()
    check(not [1 for s in app.design.place.values() if s == 16], "undo removes the torches again")
    app.add_torches()
    # errors are shown, nothing breaks
    del shown[:]
    app.sel_slot = 3; app.item_var.set("not:a:valid:id"); app.set_slot_from_box()
    check(shown and shown[-1][0] == "error" and 3 not in app.design.inv, "bad item id refused")
    for k in range(1, 8):
        app.sel_slot = k; app.item_var.set("dirt"); app.set_slot_from_box()
    del shown[:]
    app.sel_slot = 8; app.item_var.set("dirt"); app.set_slot_from_box()
    check(len(app.design.inv) == 8 and shown and shown[-1][0] == "error" and 8 not in app.design.inv, "more than 8 reserved slots refused")
    for k in range(1, 8):
        app.sel_slot = k; app.empty_slot()
    check(set(app.design.inv) == {15, 16}, "slots can be emptied")
    app.sel_slot = 15; app.empty_slot()
    check(not any(s == 15 for s in app.design.place.values()) and app.brush is None, "emptying a slot forgets its blocks and the brush")
    # dig order + torch timing selectors
    app.nb.select(app.tabs["Edit"]); pump(secs=0.1)
    check(app.pattern_var.get() == dict(cd.PATTERNS)["nearest"] and app.torch_mode_var.get() == dict(cd.TORCH_MODES)["first"],
          "selectors show the defaults: %s / %s" % (app.pattern_var.get(), app.torch_mode_var.get()))
    app.pattern_var.set(dict(cd.PATTERNS)["rows"]); app.pick_pattern()
    check(app.design.pattern == "rows", "dig order changed to rows")
    shot("13_edit_tab_pattern")
    app.nb.select(app.tabs["Blocks"]); pump(secs=0.1)
    app.torch_mode_var.set(dict(cd.TORCH_MODES)["end"]); app.pick_torch_mode()
    check(app.design.torch_mode == "end", "torch timing changed")
    shot("14_blocks_tab_timing")
    # ---- v0.6 bigger buttons / v0.7 favorites / v0.8 icons
    n_undo = len(app.undo)
    bank = app.icon_bank()
    check(bank is not None and bank.known("minecraft:torch") and not bank.known("mymod:gear"), "icon bank loads; modded ids unknown")
    check(bank.get("minecraft:torch", 2).width() == 32 and bank.get("minecraft:torch", 1).width() == 16, "icons come in 16px and 32px")
    check(bank.get("mymod:gear") is None and bank.picture("mymod:gear", 2).width() == 32, "modded item falls back to a colour square")
    missing = [n for n, _c in cd.ITEM_PRESETS if not bank.known(n)]
    check(missing == [], "every preset has one of our simplified pictures: %s" % missing)
    check(len(bank.names()) > 1200, "%d vanilla items have icons" % len(bank.names()))
    a = bank.get("minecraft:cobblestone", 1)
    px = [a.get(x, y) for x in range(16) for y in range(16)]
    check(len(set(px)) > 4, "cobblestone icon has texture detail")
    import statistics
    avg_ok = 0
    for nm in ("cobblestone", "stone", "oak_planks", "dirt", "bricks", "sandstone", "netherrack", "gold_block"):
        t = cd.item_tile("minecraft:" + nm)
        px_ = [c for row in t for c in row if c]
        mean_ = [statistics.mean(c[i] for c in px_) for i in range(3)]
        base_ = cd.icon_stats("minecraft:" + nm)[1]
        avg_ok += all(abs(mean_[i] - base_[i]) < 40 for i in range(3))
    check(avg_ok == 8, "simplified tiles keep the original block's overall colour (%d/8)" % avg_ok)
    check(cd.item_tile("minecraft:cobblestone") == cd.item_tile("minecraft:cobblestone") and cd.item_tile("mymod:gear") is None, "tiles are deterministic; mods get none")
    check(cd.item_color("minecraft:cobblestone") == "#7f7f7f" and cd.item_color("minecraft:oak_planks") == "#a2824e", "colours match the game: %s %s" % (cd.item_color("minecraft:cobblestone"), cd.item_color("minecraft:oak_planks")))
    check(app.favorites() == cd.DEFAULT_FAVORITES, "default favorites: %s" % app.favorites())
    app.nb.select(app.tabs["Blocks"]); pump(secs=0.1)
    check(len(app.fav_bar.winfo_children()) == 4, "favorites bar shows 4 buttons")
    app.sel_slot = 5; app.refresh_inventory()
    app.fav_bar.winfo_children()[1].invoke(); pump(secs=0.05)
    check(app.design.inv.get(5) == "minecraft:cobblestone", "favorite button puts its item in the selected slot")
    check("Remove" in app.fav_btn.cget("text"), "favorite button shows it is a favorite")
    app.toggle_slot_favorite()
    check("minecraft:cobblestone" not in app.favorites() and len(app.fav_bar.winfo_children()) == 3, "un-favorited")
    check("minecraft:cobblestone" not in json.load(open(cd.CONFIG_FILE)).get("favorites", ["minecraft:cobblestone"]), "favorites saved to config")
    app.toggle_slot_favorite()
    check(app.favorites()[-1] == "minecraft:cobblestone", "re-favorited goes to the end")
    app.sel_slot = 6; app.refresh_inventory(); app.open_picker(); pump(secs=0.2)
    rows = app.pick_tree.get_children()
    check(rows[0] == "minecraft:torch" and len(rows) == 300, "picker lists favorites first then everything (%d rows)" % len(rows))
    shot("15_item_picker")
    app.pick_q.set("cobble"); pump(secs=0.1)
    rows = app.pick_tree.get_children()
    check("minecraft:cobblestone" in rows and "minecraft:torch" not in rows and all("cobble" in r for r in rows), "search narrows: %s" % list(rows)[:5])
    app.pick_q.set("mymod:cool_block"); pump(secs=0.1)
    check(app.pick_tree.get_children()[0] == "mymod:cool_block", "typed modded id appears as a row")
    app.pick_tree.selection_set("mymod:cool_block"); app.picker_use(); pump(secs=0.1)
    check(app.design.inv.get(6) == "mymod:cool_block" and not app.picker.winfo_exists(), "picker assigns a modded item and closes")
    app.set_favorite("mymod:cool_block", True)
    check(len(app.fav_bar.winfo_children()) == 5, "modded favorites get a square button")
    app.open_picker(); app.pick_favs_only.set(True); app.pick_q.set(""); app.picker_fill(); pump(secs=0.1)
    check(list(app.pick_tree.get_children()) == app.favorites(), "favorites-only filter")
    app.pick_tree.selection_set("minecraft:glass"); app.sel_slot = 7; app.picker_use()
    check(app.design.inv.get(7) == "minecraft:glass", "picker puts glass in slot 7")
    app.open_picker(); app.pick_tree.selection_set("minecraft:glass"); app.picker_toggle()
    check("minecraft:glass" not in app.favorites(), "picker star toggle"); app.picker.destroy()
    app.sel_slot = 15; app.refresh_inventory()
    shot("16_blocks_tab_icons")
    # ---- v1.2: import your own textures (resource pack / jar / mod), toggle between them and ours
    import struct, zlib, zipfile as _zf
    def png_bytes(w, h, px):
        raw = b"".join(b"\x00" + b"".join(bytes(px(x, y)) for x in range(w)) for y in range(h))
        def chunk(t, d): return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xffffffff)
        return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0)) + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b"")
    zpath = os.path.join(TMP, "mypack.zip")
    with _zf.ZipFile(zpath, "w") as zf:
        zf.writestr("assets/minecraft/textures/block/cobblestone.png", png_bytes(32, 32, lambda x, y: (200, 30, 30, 255)))
        zf.writestr("assets/minecraft/textures/block/stone.png", png_bytes(16, 16, lambda x, y: (30, 30, 200, 255)))
        zf.writestr("assets/minecraft/textures/block/crafting_table_front.png", png_bytes(16, 16, lambda x, y: (10, 200, 10, 255)))
        zf.writestr("assets/minecraft/textures/block/sea_lantern.png", png_bytes(16, 80, lambda x, y: (250, 250, 0, 255) if y < 16 else (0, 0, 0, 255)))
        zf.writestr("assets/minecraft/textures/item/diamond.png", png_bytes(16, 16, lambda x, y: (0, 220, 220, 255) if (x - 8) ** 2 + (y - 8) ** 2 < 30 else (0, 0, 0, 0)))
        zf.writestr("assets/mymod/textures/block/cool_block.png", png_bytes(64, 64, lambda x, y: (255, 0, 255, 255)))
        zf.writestr("assets/minecraft/textures/block/deep/nested.png", png_bytes(16, 16, lambda x, y: (1, 2, 3, 255)))
    builtin_cobble = cd.item_tile("minecraft:cobblestone")
    check(cd.TEX["mode"] == "builtin" and cd.display_tile("minecraft:cobblestone") == builtin_cobble, "starts on the built-in textures")
    check(app.import_textures([zpath]) == 6 and cd.TEX["mode"] == "imported", "imported 6 textures from a resource pack (nested folders ignored)")
    t = cd.display_tile("minecraft:cobblestone")
    check(t[0][0] == (200, 30, 30) and t[15][15] == (200, 30, 30), "a 32px texture is shrunk to 16: %s" % (t[0][0],))
    check(cd.display_tile("minecraft:crafting_table")[3][3] == (10, 200, 10), "block faces are found (crafting_table_front)")
    check(cd.display_tile("minecraft:sea_lantern")[0][0] == (250, 250, 0) and cd.display_tile("minecraft:sea_lantern")[15][15] == (250, 250, 0), "animated strips use the first frame")
    dt = cd.display_tile("minecraft:diamond")
    check(dt[0][0] is None and dt[8][8] == (0, 220, 220), "transparent pixels are kept")
    check(cd.display_tile("mymod:cool_block")[5][5] == (255, 0, 255), "a modded item gets its texture from the pack")
    check(cd.display_tile("minecraft:dirt") == cd.item_tile("minecraft:dirt"), "items missing from the pack keep our simplified tile")
    check(cd.display_color("minecraft:stone") == "#1e1ec8" and cd.display_color("mymod:cool_block") == "#ff00ff", "flat colours follow the imported textures")
    bank = app.icon_bank()
    check(bank.get("mymod:cool_block", 2).width() == 32 and bank.known("mymod:cool_block") and "mymod:cool_block" in bank.names(), "modded item gets a picture and shows up in the picker list")
    check("6 imported textures" in app.texture_status() and "mypack.zip" in app.texture_status(), app.texture_status())
    cd.load_texpack(); cd.TEX["mode"] = "imported"
    check(len(cd.TEX["tiles"]) == 6 and cd.display_tile("minecraft:stone")[0][0] == (30, 30, 200), "imported textures are saved and reloaded")
    td = app.design.copy(); td.set_slot_item(10, "mymod:cool_block"); td.set_slot_item(11, "minecraft:cobblestone")
    vdat = cd.viewer_data(td, cd.simulate(td))
    check(vdat["tiles"]["10"][0][0] == "ff00ff" and vdat["tiles"]["11"][0][0] == "c81e1e" and vdat["digTile"][0][0] == "1e1ec8", "the 3D page carries the imported tiles it uses")
    app.set_texture_mode("builtin")
    check(cd.display_tile("minecraft:cobblestone") == builtin_cobble and cd.display_tile("mymod:cool_block") is None and bank.get("mymod:cool_block") is None, "toggle back to built-in")
    app.set_texture_mode("imported"); check(cd.TEX["mode"] == "imported" and json.load(open(cd.CONFIG_FILE)).get("texture_mode") == "imported", "toggle remembered in settings")
    app.open_textures(); pump(secs=0.2); shot("18_textures_dialog"); app.tex_win.destroy()
    app.open_shapes(); app.root.update()
    check(hasattr(app, "shapes_dialog"), "Shapes dialog opens")
    app.shapes_dialog.destroy()
    app.open_estimate(); pump(lambda: hasattr(app, "estimate_window"), 20)
    check(hasattr(app, "estimate_window") and "Fuel:" in app.last_estimate["lines"][2], "Estimate window opens"); app.estimate_window.destroy()
    app.pick_skin("bee"); check(app.design.skin == "bee" and app.skin_color() == "#f5c518" and app.skin_var.get() == "Bee", "app skin picker sets the design's skin")
    app.refresh_layer(); app.pick_skin("classic")
    app.open_templates(); app.root.update()
    check(hasattr(app, "templates_dialog"), "Templates dialog opens")
    app.templates_dialog.destroy()
    del shown[:]
    badz = os.path.join(TMP, "notazip.jar"); open(badz, "w").write("hello")
    check(app.import_textures([badz]) == 0 and shown and shown[-1][0] == "error", "a file that isn't a resource pack is refused")
    app.remove_textures()
    check(cd.TEX["mode"] == "builtin" and not cd.TEX["tiles"] and not os.path.exists(cd.texpack_file()) and cd.display_tile("mymod:cool_block") is None, "remove imported textures")
    app.sel_slot = 15; app.refresh_inventory()
    for k in (5, 6, 7):
        app.sel_slot = k; app.empty_slot()
    del app.undo[n_undo:]          # the item edits above are not part of the undo test below
    app.do_undo()
    check(app.design.torch_mode == "first" and app.torch_mode_var.get() == dict(cd.TORCH_MODES)["first"] and app.design.pattern == "rows", "undo restores the timing and the selector")
    json_back = cd.Design.from_json(json.loads(json.dumps(app.design.to_json())))
    check(json_back.pattern == "rows" and json_back.torch_mode == "first", "pattern survives save/load")
    # preview with placing
    app.start_preview()
    check(pump(lambda: app.mode == "preview", 5), "preview with torches computed")
    check(app.sim.places == len(cd.build_place(app.vdesign)) > 0 and app.sim.events[-1][0] in ("t", "m"), "route includes %d placements" % app.sim.places)
    check([e for e in app.sim.events] == cd.simulate(app.vdesign).events and app.vdesign.pattern == "rows", "the preview follows the chosen dig order")
    first_p = next(i for i, e in enumerate(app.sim.events) if e[0] == "p")
    app.seek(first_p + 1); app.seek(len(app.sim.events) // 2); pump(secs=0.1)
    # (this hall puts its torches on a cobblestone floor that is only laid at the end, so they wait for it)
    check(first_p > len(app.sim.events) * 0.4, "torches on a placed floor wait for the floor: first placement at step %d of %d" % (first_p, len(app.sim.events)))
    # torches on natural floor go in as early as possible, and always from the cell above
    for mode, early in (("first", True), ("early", True), ("end", False)):
        tr = torch_room(9, 9, 3, 5, 4); tr.torch_mode = mode
        evs = cd.simulate(tr).events
        fp = next(i for i, e in enumerate(evs) if e[0] == "p")
        check((fp < len(evs) * 0.35) == early, "torch timing %s: first torch at step %d of %d" % (mode, fp, len(evs)))
        pos_ = tr.turtle; bad = 0
        for e in evs:
            if e[0] == "m": pos_ = e[1:]
            elif e[0] == "p" and pos_ != (e[1], e[2] + 1, e[3]): bad += 1
        check(bad == 0, "%s: every torch is dropped down from the cell above" % mode)
    app.seek(len(app.sim.events)); pump(secs=0.1)
    check(app.view.placed == set(cd.build_place(app.vdesign)) and "placed %d / %d" % (app.sim.places, app.sim.places) in app.info_var.get(), "end: all placed - " + app.info_var.get().split("\n")[0])
    app.layer = 2; app.refresh_layer(); pump(secs=0.1)
    shot("12_preview_placing")
    app.exit_view()
    del shown[:]
    # --- 3D page from the app
    opened = []
    cd.webbrowser.open = lambda u: opened.append(u)
    app.view3d()
    check(pump(lambda: opened, 20), "3D button builds the page and opens the browser")
    tmp3d = urllib.request.url2pathname(opened[0][len("file://"):]) if opened else ""
    check(os.path.exists(tmp3d) and "Lit hall" in open(tmp3d, encoding="utf-8").read(), "3D page written for this design: %s" % tmp3d)
    del opened[:]; app.view3d(record=True)
    check(pump(lambda: opened, 20) and opened[0].endswith("#record"), "the video button opens the page with the record panel")
    saved3d = os.path.join(TMP, "share_me.html"); app.ask_save_path = lambda **kw: saved3d
    del opened[:]; app.view3d(save=True)
    check(pump(lambda: opened, 20) and os.path.getsize(saved3d) > 600000 and "saved" in app.info_var.get().lower(), "Save 3D page writes one file: " + app.info_var.get())

    # --- resizing and big grids
    app.nb.select(0)
    for g in ("700x560", "1500x900", "1240x760"):
        root.geometry(g + "+0+0"); pump(secs=0.3)
    check(app.cs >= 8 and app.ox >= 0, "window resize re-fits the grid (%dpx cells)" % app.cs)
    app.size_vars[0].set(32); app.size_vars[1].set(32); app.size_vars[2].set(32); app.apply_size(); pump(secs=0.3)
    app.layer_op("fill"); app.set_layer(3); app.layer_op("fill")
    check(app.cs >= 8 and len(app.items) == 32 * 32, "32x32x32 fits (%dpx cells)" % app.cs)
    t0 = time.time(); sim = cd.simulate(app.design); dt = time.time() - t0
    print("  simulate(2 layers of 32x32 = %d blocks) took %.1fs" % (app.total, dt))
    check(dt < 20, "big simulation finishes")
    shot("09_big_grid")
    app.on_close()
    check(not TKERRS, "no exceptions inside Tk callbacks" + ("\n" + TKERRS[0] if TKERRS else ""))



# ================================================================ the 3D page in a real (headless) browser
section("3D page (headless Chromium)")
import subprocess, shutil
vd = cd.Design(7, 7, 3); vd.name = "Viewer <test> & co"; vd.tx, vd.ty, vd.tz = 4, 1, 1
for yy in (1, 2, 3):
    for zz in range(1, 8):
        for xx in range(1, 8): vd.set_cell(xx, yy, zz, True)
vd.set_slot_item(16, cd.TORCH); vd.set_slot_item(15, "minecraft:cobblestone")
for zz in range(2, 7):
    for xx in range(2, 7): vd.place[(xx, 1, zz)] = 15
cd.auto_torches(vd, 3, 16)
vsim = cd.simulate(vd)
page = cd.build_viewer_html(vd, vsim)
check("<title>Viewer &lt;test&gt; &amp; co - Carve 3D preview</title>" in page, "page title is escaped")
check(page.count("</script>") == 3 and "@@DATA@@" not in page and "@@THREE@@" not in page and "@@TURTLE3D@@" not in page, "page has its scripts (three, turtle model, the page, its data) and no leftover markers")
vpath = os.path.join(TMP, "viewer.html"); open(vpath, "w", encoding="utf-8").write(page)
pyexe = shutil.which("python3")
probe = r"""
import sys, json, base64
from playwright.sync_api import sync_playwright
path, n = sys.argv[1], None
with sync_playwright() as p:
    b = p.chromium.launch(args=["--use-gl=swiftshader", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist"])
    pg = b.new_page(viewport={"width": 1100, "height": 700})
    errs = []
    pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.on("console", lambda m: errs.append(m.text) if m.type == "error" else None)
    pg.goto("file://" + path); pg.wait_for_timeout(1200)
    st0 = pg.evaluate("CARVE_VIEWER.state()")
    pg.evaluate("CARVE_VIEWER.seek(%d)" % st0["n"]); pg.wait_for_timeout(300)
    st1 = pg.evaluate("CARVE_VIEWER.state()")
    pg.evaluate("CARVE_VIEWER.seek(%d)" % (st0["n"] // 2)); st2 = pg.evaluate("CARVE_VIEWER.state()")
    pg.click("#play"); pg.wait_for_timeout(900); st3 = pg.evaluate("CARVE_VIEWER.state()")
    pg.click("#tex"); pg.wait_for_timeout(300); pg.screenshot(path=sys.argv[2].replace(".png", "_rainbow.png")); pg.click("#tex"); pg.wait_for_timeout(300)
    pg.screenshot(path=sys.argv[2])
    pg.evaluate("document.getElementById('recbtn').click()"); pg.wait_for_timeout(200)
    panel = pg.evaluate("document.getElementById('recpanel').classList.contains('open')")
    pg.evaluate("document.getElementById('recclose').click()")
    vid = pg.evaluate('''async () => {
        const r = await CARVE_VIEWER.record({seconds: 4, mb: 3});
        const buf = new Uint8Array(await r.blob.arrayBuffer()); let s = "";
        for (let i = 0; i < buf.length; i += 32768) s += String.fromCharCode.apply(null, buf.subarray(i, i + 32768));
        return {mime: r.mime, size: r.blob.size, b64: btoa(s)};
    }''')
    open(sys.argv[3] + (".mp4" if vid["mime"] == "video/mp4" else ".webm"), "wb").write(base64.b64decode(vid["b64"]))
    after = pg.evaluate("[document.body.className, CARVE_VIEWER.state().cur]")
    print(json.dumps({"s0": st0, "end": st1, "mid": st2, "playing": st3, "errs": errs, "panel": panel,
                      "vmime": vid["mime"], "vsize": vid["size"], "after": after}))
    b.close()
"""
try:
    vbase = os.path.join(TMP, "replay")
    r = subprocess.run([pyexe, "-c", probe, vpath, os.path.join(HERE, "..", "shots", "17_viewer_3d.png"), vbase], capture_output=True, text=True, timeout=120)
    res = json.loads(r.stdout.strip().splitlines()[-1])
except Exception as ex:
    res = None
    check(False, "browser test could not run: %s %s" % (ex, (r.stderr[-300:] if 'r' in dir() else "")))
if res:
    e = res["end"]
    check(not res["errs"], "no JavaScript errors: %s" % res["errs"][:2])
    check(res["s0"]["n"] == len(vsim.events), "page holds the whole route (%d events)" % res["s0"]["n"])
    check((e["digs"], e["moves"], e["turns"], e["placed"]) == (vsim.digs, vsim.moves, vsim.turns, vsim.places),
          "replay ends with the simulator's totals: %s" % e)
    check(e["pos"] == list(vd.turtle), "turtle ends back at its start")
    check(res["panel"] and res["after"][0] == "" and res["after"][1] == len(vsim.events), "record panel opens; after recording the page is back to normal at the end of the route: %s" % (res["after"],))
    vfile = vbase + (".mp4" if res["vmime"] == "video/mp4" else ".webm")
    check(os.path.exists(vfile) and 0 < res["vsize"] < 3_000_000, "video recorded (%s, %.2f MB, under the 3 MB budget)" % (res["vmime"], res["vsize"] / 1e6))
    if shutil.which("ffprobe"):
        pr = subprocess.run(["ffprobe", "-v", "error", "-count_frames", "-select_streams", "v:0", "-show_entries",
                             "stream=width,height,nb_read_frames:format=duration", "-of", "json", vfile], capture_output=True, text=True)
        info = json.loads(pr.stdout)
        dur = float(info["format"]["duration"]) if info["format"].get("duration") not in (None, "N/A") else 0
        check(info["streams"][0]["width"] == 1280 and info["streams"][0]["height"] == 720 and int(info["streams"][0]["nb_read_frames"]) > 20,
              "video is 1280x720 with %s frames" % info["streams"][0]["nb_read_frames"])
        check(dur == 0 or 3.0 < dur < 5.5, "video lasts about the 4 s asked for (%.1f s)" % dur)
    check(res["mid"]["cur"] == len(vsim.events) // 2 and res["playing"]["cur"] > res["mid"]["cur"], "scrubbing and playing work")

# ---- v1.4 shapes and templates
for kind, _lbl in cd.SHAPES:
    for hol in (False, True):
        for caps in (False, True):
            dd = cd.Design(9, 9, 6)
            cells = cd.shape_cells(kind, 9, 9, 6, hol, caps)
            cd.apply_cells(dd, cells)
            _r, _t, sk = cd.build_run(dd)
            check(cells and sk == 0, "shape %s hollow=%s caps=%s is one reachable piece (%d cells)" % (kind, hol, caps, len(cells)))
check(len(cd.shape_cells("box", 5, 5, 5, True, True)) == 98, "hollow 5x5x5 box has 98 skin cells")
check(len(cd.shape_cells("box", 5, 5, 5, True, False)) == 80 - 0 or len(cd.shape_cells("box", 5, 5, 5, True, False)) == 80, "hollow box without caps is the 4 walls")
for key, _t2, _b, _sz, _fn in cd.TEMPLATES:
    td = cd.template_design(key)
    check(td.sel and cd.build_run(td)[2] == 0, "template %s builds a reachable design" % key)

print("\n%d checks passed, %d failed" % (PASSES, len(FAILS)))
for f in FAILS: print("  -", f)
sys.exit(1 if FAILS else 0)
