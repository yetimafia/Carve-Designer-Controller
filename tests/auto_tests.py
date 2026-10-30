import json
"""Tests for the tree farm, auto smelter and auto crafter programs (run inside run_tests.py)."""
import os

HERE = os.path.dirname(os.path.abspath(__file__))


def run(cd, lua, check, section):
    section("v2.0-2.2 automation programs (simulated world)")
    M = lua.execute(open(os.path.join(HERE, "auto_mock.lua")).read())
    tree = cd.auto_default("treefarm")
    tree.update(cols=3, rows=2, spacing=4, bonemeal=False, cycles=2, wait=900)
    bone = dict(tree, bonemeal=True)
    one = dict(tree, cols=2, rows=2, bonemeal=True, cycles=1)
    sm = cd.auto_default("smelter")
    sm.update(once=True)
    cr = cd.auto_default("crafter")

    def craft(grid, **kw):
        return cd.generate_auto_lua(dict(cr, grid=grid, once=True, **kw))
    P = "minecraft:oak_planks"
    src = {
        "tree_live": cd.generate_auto_lua(tree, "http://127.0.0.1:8765"),
        "smelt_live": cd.generate_auto_lua(dict(sm, furnaces=1), "http://192.168.1.5:9000"),
        "miner": cd.generate_auto_lua({"kind": "miner", "name": "Miner", "depth": 8, "reach": 12, "rib": 6}, "http://127.0.0.1:8765"),
        "miner_coal": cd.generate_auto_lua({"kind": "miner", "name": "Miner", "depth": 8, "reach": 12, "rib": 6, "want": ["coal"]}),
        "hauler": cd.generate_auto_lua({"kind": "hauler", "name": "Hauler", "legs": [{"from": "My Trees", "to": "Smelter", "item": "log"}], "wait": 5, "cycles": 1}, "http://127.0.0.1:8765"),
        "keeper": cd.generate_auto_lua({"kind": "keeper", "name": "Storage keeper", "length": 3, "wait": 5, "rescan": 0}, "http://127.0.0.1:8765"),
        "foreman": cd.generate_auto_lua({"kind": "foreman", "name": "Foreman", "dispatch": True, "build": False, "jobs": [
            {"name": "Tree farm", "slug": "tree_farm", "kind": "treefarm", "furnaces": 0, "foot": None},
            {"name": "Smelter", "slug": "smelter", "kind": "smelter", "furnaces": 2, "foot": None}]}, "http://127.0.0.1:8765"),
        "foreman_build": cd.generate_auto_lua({"kind": "foreman", "name": "Foreman", "build": True, "dispatch": True,
            "agent_url": "https://raw.example/agent.lua", "launcher_url": "https://raw.example/carve.lua", "jobs": [
            {"name": "Tree farm", "slug": "tree_farm", "kind": "treefarm", "furnaces": 0, "foot": None, "kit": [["sapling", 4], ["chest", 1]], "crafty": False},
            {"name": "Compressor", "slug": "compressor", "kind": "crafter", "furnaces": 0, "foot": None, "kit": [["chest", 2]], "crafty": True}]}, "http://127.0.0.1:8765"),
        "foreman_full": cd.generate_auto_lua(dict(cd.colony_foreman(cd.colony_starter())[0], build=True, dispatch=True,
            agent_url="https://raw.example/agent.lua", launcher_url="https://raw.example/carve.lua"), "http://127.0.0.1:8765"),
        "full_materials": json.dumps(cd.colony_materials(cd.colony_foreman(cd.colony_starter()))["items"]),
        "keeper_named": cd.generate_auto_lua({"kind": "keeper", "name": "Storage keeper", "length": 3, "wait": 5, "rescan": 0, "label": "Jupiter"}),
        "hauler_off": cd.generate_auto_lua({"kind": "hauler", "name": "Hauler", "legs": [{"from": "My Trees", "to": "Smelter", "item": "log"}], "wait": 5, "cycles": 1}),
        "scout_live": cd.generate_auto_lua({"kind": "scout", "name": "Scout", "radius": 6, "up": 3, "down": 2}, "http://127.0.0.1:8765"),
        "scout_off": cd.generate_auto_lua({"kind": "scout", "name": "Scout", "radius": 6, "up": 3, "down": 2}),
        "agent_live": cd.generate_auto_lua({"kind": "agent", "name": "Agent"}, "http://127.0.0.1:8765"),
        "agent_off": cd.generate_auto_lua({"kind": "agent", "name": "Agent"}),
        "tree_wait": cd.generate_auto_lua(tree), "tree_bone": cd.generate_auto_lua(bone), "tree_one": cd.generate_auto_lua(one),
        "smelt1": cd.generate_auto_lua(dict(sm, furnaces=1)), "smelt2": cd.generate_auto_lua(dict(sm, furnaces=2)),
        "smelt3": cd.generate_auto_lua(dict(sm, furnaces=3)),
        "craft_sticks": craft([None, P, None, None, P, None, None, None, None]),
        "craft_chest": craft([P, P, P, P, None, P, P, P, P]),
        "craft_pick": craft(["minecraft:iron_ingot"] * 3 + [None, "minecraft:stick", None, None, "minecraft:stick", None]),
        "craft_limited": craft([None, P, None, None, P, None, None, None, None], total=3),
        "craft_badrecipe": craft([P, None, None, None, None, None, None, None, P]),
    }
    results = lua.globals().loadfile(os.path.join(HERE, "auto_cases.lua"))(M, lua.table_from(src))
    for r in results.values():
        check(bool(r[1]), r[2])

    # `carve start <id> <program>` from the menu program
    launcher = cd.generate_launcher("me/turtles", "main", "carve")
    probe = """function(src, urlfile)
    local printed, posted = {}, {}
    local files = { ["carve.live"] = urlfile }
    fs = { open = function(n, m)
      if m == "r" then
        if not files[n] then return nil end
        return { readAll = function() return files[n] end, close = function() end }
      end
      return { write = function() end, close = function() end }
    end }
    textutils = { serialiseJSON = function(t) return "{id=" .. t.id .. ",cmd=" .. t.cmd .. ",arg=" .. t.arg .. "}" end }
    http = { post = function(u, b) posted[#posted + 1] = u .. " " .. b; return { close = function() end } end }
    print = function(...) printed[#printed + 1] = table.concat({ ... }, " ") end
    local fn = load(src, "carve")
    local ok, err = pcall(fn, table.unpack(ARGS))
    return { ok = ok, err = tostring(err), printed = table.concat(printed, "|"), posted = table.concat(posted, "|") }
    end"""
    def start(args, urlfile="http://127.0.0.1:8765"):
        lua.globals().ARGS = lua.table_from(args)
        return lua.eval(probe)(launcher, urlfile)
    r = start(["start", "7", "my_trees"])
    check(r["ok"] and r["posted"] == "http://127.0.0.1:8765/cmd {id=7,cmd=run,arg=my_trees}" and "Asked turtle 7" in r["printed"],
          "carve start posts the order: %s %s" % (r["posted"], r["err"]))
    r = start(["start", "7"])
    check(r["posted"] == "" and "Use:" in r["printed"], "carve start needs an id and a program")
    r = start(["start", "7", "../x"])
    check(r["posted"] == "", "carve start refuses a bad program name")
    r = start(["start", "7", "x"], urlfile=None)
    check(not r["ok"] and "where the Designer app is" in r["err"], "carve start explains when it does not know the app yet")
