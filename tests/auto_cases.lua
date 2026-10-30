-- scenarios for the automation programs; returns a list of { pass, text }
local M, SRC = ...
local R = {}
local function check(c, text) R[#R + 1] = { c and true or false, text } end
local function key(...) return M.key(...) end

local function atHome() local x, y, z = M.turtle(); return x == 0 and y == 0 and z == 0 end

------------------------------------------------------------- tree farm
local function field(cols, rows, S, extra)
  local spec = { fuel = extra and extra.fuel or 500, items = { { 1, "minecraft:oak_sapling", cols * rows + 2 } } }
  M.reset(spec)
  M.floor(-2, S * (cols + 2), -3, S * rows + 3, -1)
  M.setBlock(0, 0, -1, "minecraft:chest", {})
end

for _, bone in ipairs({ false, true }) do
  local label = bone and "tree farm with bone meal" or "tree farm waiting for growth"
  field(3, 2, 4)
  if bone then M.addItem("minecraft:bone_meal", 40) end
  -- bone meal goes to slot 2: addItem puts it in the first free slot, which is 2
  local ok, err = M.runMain(bone and SRC.tree_bone or SRC.tree_wait)
  check(ok, label .. " runs to the end: " .. tostring(err))
  check(atHome(), label .. ": turtle ends at the start")
  local logs = M.chestCount(0, 0, -1, "minecraft:oak_log")
  check(logs + (M.burned or 0) >= 24 and logs > 0, label .. ": all 24 logs gathered - " .. logs .. " in the chest, " .. tostring(M.burned) .. " burned for fuel")
  check((M.planted or 0) >= 12, label .. ": replants after chopping (" .. tostring(M.planted) .. " planted)")
  check(#M.errors == 0 and not M.dugProtected, label .. ": no errors, the chest was never dug")
  check(not M.files["startup.lua"] and not M.files["carve.farm"], label .. ": removes its restart files at the end")
end

field(2, 2, 4)
M.addItem("minecraft:bone_meal", 40)
M.abortAfter(150)
local ok = M.runMain(SRC.tree_one)
check(not ok and M.files["startup.lua"] and M.files["carve.farm"], "tree farm: Ctrl+T leaves a restart file")
local ok2, err2 = M.runMain(SRC.tree_one, "resume")
check(ok2, "tree farm: resumes after the interruption: " .. tostring(err2))
check(atHome() and M.chestCount(0, 0, -1, "minecraft:oak_log") > 0, "tree farm: the resumed run finishes at the start with logs stored")
M.files["startup.lua"] = "-- carve auto\nshell.run('x')\n"
M.runMain(SRC.tree_one, "stop")
check(not M.files["startup.lua"], "tree farm: 'stop' removes the automatic restart")
-- never overwrite somebody else's startup file
field(1, 1, 4)
M.files["startup.lua"] = "print('mine')"
M.abortAfter(20)
M.runMain(SRC.tree_one)
check(M.files["startup.lua"] == "print('mine')", "tree farm: leaves a foreign startup.lua alone")

-- saplings anywhere in the inventory are found, even of another kind
M.reset({ fuel = 500, items = { { 7, "minecraft:oak_sapling", 6 } } })
M.floor(-2, 14, -3, 12, -1); M.setBlock(0, 0, -1, "minecraft:chest", {})
M.abortAfter(300)
M.runMain(SRC.tree_one)
check((M.planted or 0) >= 3, "tree farm: finds saplings in any slot (" .. tostring(M.planted) .. " planted)")
M.reset({ fuel = 500, items = { { 9, "minecraft:spruce_sapling", 6 } } })
M.floor(-2, 14, -3, 12, -1); M.setBlock(0, 0, -1, "minecraft:chest", {})
M.abortAfter(300)
M.runMain(SRC.tree_one)
check((M.planted or 0) >= 3, "tree farm: plants whatever sapling it has when the chosen kind is missing (" .. tostring(M.planted) .. " planted)")
M.reset({ fuel = 500, items = { { 2, "minecraft:oak_sapling", 64 }, { 11, "minecraft:oak_sapling", 20 } } })
M.floor(-2, 14, -3, 12, -1); M.setBlock(0, 0, -1, "minecraft:chest", {})
M.abortAfter(900)
M.runMain(SRC.tree_one)
check(M.chestCount(0, 0, -1, "minecraft:oak_sapling") == 0, "tree farm: saplings in several stacks never end up in the log chest")
M.reset({ fuel = 500, items = {} })
M.floor(-2, 14, -3, 12, -1); M.setBlock(0, 0, -1, "minecraft:chest", {})
M.abortAfter(40)
M.runMain(SRC.tree_one)
check((M.planted or 0) == 0 and not M.digs, "tree farm: with no saplings at all it waits for some instead of walking off")

------------------------------------------------------------- smelter
local function smelterRoom(F, items, fuelStacks)
  M.reset({ fuel = 800 })
  M.setBlock(0, 0, -1, "minecraft:chest", items)
  M.setBlock(-1, 0, 0, "minecraft:chest", {})
  for k = 1, F do M.setBlock(k - 1, 0, 2, "minecraft:furnace") end
end
smelterRoom(3, { { "minecraft:coal", 32 }, { "minecraft:raw_iron", 64 }, { "minecraft:cobblestone", 20 }, { "minecraft:raw_gold", 5 } })
local ok3, err3 = M.runMain(SRC.smelt3)
check(ok3, "smelter runs to the end: " .. tostring(err3))
check(atHome(), "smelter: ends at the start")
check(M.chestCount(-1, 0, 0, "minecraft:iron_ingot") == 64, "smelter: 64 iron ingots in the output chest (" .. M.chestCount(-1, 0, 0, "minecraft:iron_ingot") .. ")")
check(M.chestCount(-1, 0, 0, "minecraft:stone") == 20 and M.chestCount(-1, 0, 0, "minecraft:gold_ingot") == 5, "smelter: stone and gold too")
check(M.chestCount(0, 0, -1, "minecraft:raw_iron") == 0, "smelter: input chest emptied")
check(not M.dugProtected and #M.errors == 0, "smelter: never dug a furnace or chest")
-- more stacks than furnaces -> several rounds
smelterRoom(2, { { "minecraft:coal", 40 }, { "minecraft:raw_iron", 64 }, { "minecraft:raw_iron", 64 }, { "minecraft:raw_copper", 30 }, { "minecraft:sand", 10 } })
local ok4, err4 = M.runMain(SRC.smelt2)
check(ok4 and M.chestCount(-1, 0, 0, "minecraft:iron_ingot") == 128 and M.chestCount(-1, 0, 0, "minecraft:copper_ingot") == 30
      and M.chestCount(-1, 0, 0, "minecraft:glass") == 10, "smelter: 5 stacks through 2 furnaces over several rounds (" .. tostring(err4) .. ")")
-- no fuel but logs: burns some logs to make the first charcoal
smelterRoom(1, { { "minecraft:oak_log", 64 } })
local okB, errB = M.runMain(SRC.smelt1)
local charcoalMade = M.chestCount(-1, 0, 0, "minecraft:charcoal") + M.invCount("minecraft:charcoal")
check(okB and charcoalMade == 38 and M.chestCount(0, 0, -1, "minecraft:oak_log") == 0, "smelter: with only logs it burns 26 of them to turn 38 into charcoal (" .. charcoalMade .. ") " .. tostring(errB))
-- a decent charcoal supply: burns that, not coal or logs
smelterRoom(1, { { "minecraft:raw_iron", 16 }, { "minecraft:oak_log", 10 } })
M.addItem("minecraft:charcoal", 40); M.addItem("minecraft:coal", 10)
local okS = M.runMain(SRC.smelt1)
check(okS and M.chestCount(-1, 0, 0, "minecraft:iron_ingot") == 16 and M.invCount("minecraft:coal") == 10 and M.invCount("minecraft:charcoal") + M.chestCount(-1, 0, 0, "minecraft:charcoal") >= 38,
      "smelter: with 40 charcoal in hand it burns charcoal and leaves the coal alone (coal " .. M.invCount("minecraft:coal") .. ")")
-- earth where a chest should go: it digs it out and places the chest
M.reset({ fuel = 300, items = { { 1, "minecraft:chest", 2 } } })
M.setBlock(0, 0, -1, "minecraft:dirt"); M.setBlock(-1, 0, 0, "minecraft:stone")
M.runMain(SRC.smelt1, "setup")
check(M.block(0, 0, -1) and M.block(0, 0, -1).name == "minecraft:chest" and M.block(-1, 0, 0) and M.block(-1, 0, 0).name == "minecraft:chest",
      "smelter: puts its chests where there was dirt and stone (dug out first)")

-- unsmeltable junk does not hang it
smelterRoom(2, { { "minecraft:coal", 10 }, { "minecraft:dirt", 12 }, { "minecraft:raw_iron", 8 } })
local ok5, err5 = M.runMain(SRC.smelt2)
check(ok5 and M.chestCount(-1, 0, 0, "minecraft:iron_ingot") == 8, "smelter: junk in the chest does not hang it (" .. tostring(err5) .. ")")
-- setup places the chests and the furnaces
M.reset({ fuel = 500, items = { { 1, "minecraft:chest", 2 }, { 3, "minecraft:furnace", 3 } } })
M.runMain(SRC.smelt3, "setup")
local placed = M.count(function(b) return b.name == "minecraft:furnace" end)
check(placed == 3 and atHome(), "smelter setup: places the furnaces in a row (" .. placed .. ")")
check(M.block(0, 0, 2) and M.block(1, 0, 2) and M.block(2, 0, 2), "smelter setup: at the right cells")
check(M.block(0, 0, -1) and M.block(0, 0, -1).name == "minecraft:chest" and M.block(-1, 0, 0) and M.block(-1, 0, 0).name == "minecraft:chest",
      "smelter setup: places its own input (behind) and output (left) chests from slot 1")
M.reset({ fuel = 500, items = { { 1, "minecraft:chest", 2 } } })
M.runMain(SRC.smelt3, "setup")
check(M.count(function(b) return b.name == "minecraft:furnace" end) == 0 and M.screen[3] ~= nil, "smelter setup: asks for furnaces when it has none")
M.reset({ fuel = 500 })
local okW = M.runMain(SRC.smelt3, "setup")
local waitedMsg = false
for _, line in pairs(M.screen) do if tostring(line):find("I need a chest", 1, true) then waitedMsg = true end end
check(not okW and waitedMsg, "smelter: with no chest anywhere it says it needs one and waits")
-- low fuel: burns the coal it carries
smelterRoom(1, { { "minecraft:coal", 20 }, { "minecraft:raw_iron", 16 } })
local ok6 = M.runMain(SRC.smelt1)
check(ok6 and M.chestCount(-1, 0, 0, "minecraft:iron_ingot") == 16, "smelter: works with a single furnace")

------------------------------------------------------------- crafter
local RECIPES = {
  { grid = { "-", "oak_planks", "-", "-", "oak_planks", "-", "-", "-", "-" }, out = "stick", count = 4 },
  { grid = { "oak_planks", "oak_planks", "oak_planks", "oak_planks", "-", "oak_planks", "oak_planks", "oak_planks", "oak_planks" }, out = "chest", count = 1 },
  { grid = { "iron_ingot", "iron_ingot", "iron_ingot", "-", "stick", "-", "-", "stick", "-" }, out = "iron_pickaxe", count = 1 },
}
local function craftRoom(items)
  M.reset({ fuel = 100, recipes = RECIPES })
  M.setBlock(0, 0, -1, "minecraft:chest", items)
  M.setBlock(-1, 0, 0, "minecraft:chest", {})
end
craftRoom({ { "minecraft:oak_planks", 64 }, { "minecraft:oak_planks", 20 }, { "minecraft:dirt", 3 } })
local okc, errc = M.runMain(SRC.craft_sticks)
check(okc, "crafter runs: " .. tostring(errc))
local sticks = M.chestCount(-1, 0, 0, "minecraft:stick")
check(sticks == 4 * 42, "crafter: sticks from 84 planks (" .. sticks .. ")")
check(M.chestCount(-1, 0, 0, "minecraft:dirt") == 3 and M.chestCount(0, 0, -1, "minecraft:oak_planks") == 0, "crafter: junk goes out, no ingredient is lost")
check(M.invCount() == 0 and atHome(), "crafter: nothing left in the turtle")
craftRoom({ { "minecraft:oak_planks", 40 } })
M.runMain(SRC.craft_chest)
check(M.chestCount(-1, 0, 0, "minecraft:chest") == 5 and M.chestCount(0, 0, -1, "minecraft:oak_planks") == 0, "crafter: a ring recipe (5 chests from 40 planks)")
craftRoom({ { "minecraft:iron_ingot", 6 }, { "minecraft:stick", 5 } })
M.runMain(SRC.craft_pick)
check(M.chestCount(-1, 0, 0, "minecraft:iron_pickaxe") == 2 and M.chestCount(0, 0, -1, "minecraft:iron_ingot") == 0, "crafter: two ingredient kinds in the right cells")
craftRoom({ { "minecraft:oak_planks", 64 } })
M.runMain(SRC.craft_limited)
check(M.chestCount(-1, 0, 0, "minecraft:stick") == 12 and M.chestCount(0, 0, -1, "minecraft:oak_planks") == 58, "crafter: stops after the number of crafts asked for")
craftRoom({ { "minecraft:oak_planks", 1 } })
M.runMain(SRC.craft_sticks)
check(M.crafted == nil and M.chestCount(0, 0, -1, "minecraft:oak_planks") == 1, "crafter: too few ingredients -> nothing crafted, items back")
craftRoom({ { "minecraft:oak_planks", 8 } })
M.runMain(SRC.craft_badrecipe)
check(M.chestCount(0, 0, -1, "minecraft:oak_planks") == 8 and M.screen[3] ~= nil, "crafter: a recipe that does not match stops with a message and returns the items")
craftRoom({ { "minecraft:oak_planks", 8 } })
M.noCraft = true
local nc = M.runMain(SRC.craft_sticks)
check(M.chestCount(-1, 0, 0, "minecraft:stick") == 0 and M.chestCount(0, 0, -1, "minecraft:oak_planks") == 8, "crafter: a turtle without a crafting table says so and touches nothing")
------------------------------------------------------------- fleet reporting
local function lastPost() return M.posts[#M.posts] and M.posts[#M.posts].body or "" end
field(2, 2, 4)
M.addItem("minecraft:bone_meal", 40)
local okL, errL = M.runMain(SRC.tree_live)
check(okL, "reporting tree farm still finishes: " .. tostring(errL))
check(#M.posts >= 3 and M.posts[1].url == "http://127.0.0.1:8765/status", "reports go to <address>/status (" .. #M.posts .. " posts)")
check(lastPost():find('"kind":"treefarm"', 1, true) and lastPost():find('"id":5', 1, true) and lastPost():find('"done":true', 1, true), "the last report says finished: " .. lastPost():sub(1, 160))
check(lastPost():find('"label":"Lumber Jack"', 1, true), "reports carry the turtle label")
field(2, 2, 4)
M.addItem("minecraft:bone_meal", 40)
M.replyAfter = 3
local okS = M.runMain(SRC.tree_live)
check(not okS and #M.posts <= 8, "'stop' in a reply ends the program (" .. #M.posts .. " posts)")
check(M.files["startup.lua"] and M.files["carve.farm"], "a Fleet stop keeps the restart files, like Ctrl+T")
field(2, 2, 4)
M.addItem("minecraft:bone_meal", 40)
M.httpDown = true
local okD, errD = M.runMain(SRC.tree_live)
check(okD, "unreachable app: the program still finishes: " .. tostring(errD))
check(#M.posts == 0, "nothing recorded while the app is down")
field(2, 2, 4)
M.addItem("minecraft:bone_meal", 40)
local okN = M.runMain(SRC.tree_wait)
check(okN and #M.posts == 0, "no live address: no reports at all")
smelterRoom(1, { { "minecraft:coal", 8 }, { "minecraft:raw_iron", 16 } })
M.runMain(SRC.smelt_live)
check(#M.posts >= 2 and M.posts[1].url == "http://192.168.1.5:9000/status" and lastPost():find('"kind":"smelter"', 1, true), "smelter reports too")

------------------------------------------------------------- scout and agent
local function scoutWorld()
  M.reset({ fuel = 5000 })
  M.floor(-8, 8, -8, 8, -1, "minecraft:grass_block")
  for x = -3, 3 do for y = 0, 1 do M.setBlock(x, y, 4, "minecraft:stone") end end
  for y = 0, 1 do M.setBlock(2, y, -2, "minecraft:oak_log") end
  M.setBlock(1, 0, 1, "minecraft:water")
end
local function posted(text)
  for _, p in ipairs(M.posts) do if p.url:find("/map$") and p.body:find(text, 1, true) then return true end end
  return false
end
scoutWorld()
local okC, errC = M.runMain(SRC.scout_live)
check(okC, "scout runs to the end: " .. tostring(errC))
check(atHome(), "scout comes back to the start")
check(not M.digs and not M.dugProtected, "scout never digs")
check(posted('[0,0,4,"minecraft:stone"]'), "scout reports the wall it saw")
check(posted('[2,0,-2,"minecraft:oak_log"]') and posted('[1,0,1,"minecraft:water"]'), "scout reports a tree trunk and water")
check(posted('"air"') and posted('[0,-1,0,"minecraft:grass_block"]'), "scout reports empty space and the ground under it")
check(not posted('[0,0,0,"minecraft:'), "scout does not report its own cell as a block")
check(not M.files["startup.lua"] and not M.files["carve.scout"], "scout cleans up its restart files")
local function cellsPosted()
  local n = 0
  for _, p in ipairs(M.posts) do
    if p.url:find("/map$") then for _ in p.body:gmatch('%[%-?%d+,%-?%d+,%-?%d+,"') do n = n + 1 end end
  end
  return n
end
local cellsOk = cellsPosted()
scoutWorld()
M.failMap = 3
M.runMain(SRC.scout_live)
check(cellsOk > 50 and cellsPosted() == cellsOk, "scout keeps map cells the app didn't get and sends them later (" .. cellsPosted() .. " of " .. cellsOk .. ")")
local far = false
for _, p in ipairs(M.posts) do if p.url:find("/map$") and (p.body:find('%[8,%-?%d+,') or p.body:find('%[%-8,%-?%d+,')) then far = true end end
check(not far, "scout stays inside its radius (it may look one block past it)")
local moved = M.moves or 0
scoutWorld()
local okO, errO = M.runMain(SRC.scout_off)
check(okO and #M.posts == 0 and atHome(), "scout works without live reporting (nothing sent): " .. tostring(errO))
check((M.moves or 0) > 50, "scout actually walked around (" .. tostring(M.moves) .. " moves)")
-- low on fuel: it must turn back with enough to get home
M.reset({ fuel = 120 })
M.floor(-8, 8, -8, 8, -1, "minecraft:grass_block")
M.abortAfter(4000)
local okF = M.runMain(SRC.scout_off)
local fx = M.stats().fuel
check(fx >= 0, "scout never runs the tank empty far from home (fuel " .. fx .. ")")

M.reset({ fuel = 100 })
M.replyQueue = { "ok run my_trees\nme 100 64 200\npeer 7 Bob 105 64 200", "ok", "ok stop\nme 100 64 200" }
local okA = M.runMain(SRC.agent_live)
check(not okA and M.shellRuns[1] == "carve my_trees", "agent runs the program it was told to: " .. tostring(M.shellRuns[1]))
local sawWorld, sawNear = false, false
for _, line in pairs(M.screen) do
  if line == "World 100 64 200" then sawWorld = true end
  if line == "Nearest Bob 5 blocks" then sawNear = true end
end
check(sawWorld, "the turtle shows its world position")
-- a turtle the foreman built: its marker file says to look for the kit chest; it empties it and eats coal
M.reset({ fuel = 0 })
M.files["carve.kit"] = "1"
M.setBlock(0, 0, 1, "minecraft:chest", { { "minecraft:coal", 16 }, { "minecraft:oak_sapling", 4 }, { "minecraft:chest", 2 } })
M.replyQueue = { "ok", "ok stop" }
M.runMain(SRC.agent_live)
check(M.files["carve.kit"] == nil and M.invCount("minecraft:oak_sapling") == 4 and M.invCount("minecraft:chest") == 2 and M.stats().fuel >= 500,
  "a built turtle takes its kit out of the chest next to it and refuels from the coal (fuel " .. tostring(M.stats().fuel) .. ")")
M.reset({ fuel = 0 })
M.files["carve.kit"] = nil
M.setBlock(0, 0, 1, "minecraft:chest", { { "minecraft:coal", 16 } })
M.replyQueue = { "ok", "ok stop" }
M.runMain(SRC.agent_live)
check(M.invCount("minecraft:coal") == 0, "an agent without the foreman's marker leaves chests alone")
M.reset({ fuel = 100 })
M.runMain(SRC.agent_off)
check(#M.shellRuns == 0 and #M.posts == 0, "agent without live reporting just says so and stops")

------------------------------------------------------------- miner
local function mineWorld(fuel)
  M.reset({ fuel = fuel or 3000 })
  M.box(-2, 16, -10, -1, -8, 8, "minecraft:stone")
  M.setBlock(0, 0, -1, "minecraft:chest", {})
  M.setBlock(1, -8, 1, "minecraft:coal_ore")
  M.setBlock(3, -9, 0, "minecraft:diamond_ore"); M.setBlock(3, -10, 0, "minecraft:diamond_ore")
  M.setBlock(7, -8, 3, "minecraft:iron_ore")
  M.setBlock(10, -8, 3, "minecraft:gold_ore")
  M.setBlock(5, -5, 5, "minecraft:emerald_ore")             -- two blocks from every tunnel: never seen
end
local function chestHas(name) return M.chestCount(0, 0, -1, name) end
mineWorld()
local okM, errM = M.runMain(SRC.miner)
check(okM, "miner runs to the end: " .. tostring(errM))
check(atHome(), "miner ends at the start")
check(chestHas("minecraft:coal") >= 1, "coal ore found and delivered (" .. chestHas("minecraft:coal") .. ")")
check(chestHas("minecraft:diamond") == 2, "the whole diamond vein is mined (" .. chestHas("minecraft:diamond") .. ")")
check(chestHas("minecraft:raw_iron") >= 1 and chestHas("minecraft:raw_gold") >= 1, "iron on the way and gold beside a tunnel")
check(M.block(5, -5, 5) ~= nil and M.block(5, -5, 5).name == "minecraft:emerald_ore", "ore it never saw is left alone")
local baseMoves = M.moves or 0
check(not M.files["startup.lua"] and not M.files["carve.miner"] and not M.files["carve.minerprog"], "miner cleans up its restart files")
check(#M.errors == 0 and not M.dugProtected, "no errors, the chest was never dug")
check(posted('"minecraft:diamond_ore"'), "finds are reported to the map")
mineWorld()
local okC2 = M.runMain(SRC.miner_coal)
check(okC2 and chestHas("minecraft:raw_iron") == 0 and chestHas("minecraft:coal") >= 1, "only the chosen resource is mined")
-- an almost full inventory: it has to make a trip to the chest and come back
mineWorld()
for i = 1, 15 do M.addItem("minecraft:thing" .. i, 1) end
local okU, errU = M.runMain(SRC.miner)
check(okU and (M.ground or 0) > 0 and (M.moves or 0) > baseMoves and chestHas("minecraft:thing1") >= 1 and chestHas("minecraft:diamond") == 2, "a full inventory: junk thrown away, a trip home, then it carries on (moves " .. tostring(M.moves) .. " vs " .. baseMoves .. "): " .. tostring(errU))
-- Ctrl+T halfway, then carry on
mineWorld()
M.abortAfter(400)
local okR = M.runMain(SRC.miner)
check(not okR and M.files["carve.miner"] and M.files["startup.lua"], "miner: Ctrl+T leaves restart files")
local okR2, errR2 = M.runMain(SRC.miner, "resume")
check(okR2 and atHome() and chestHas("minecraft:diamond") == 2, "miner: resumes and finishes: " .. tostring(errR2))

-- an agent that is sent to a site walks there first (climbing over what is in the way) and faces the right way
M.reset({ fuel = 500 })
M.floor(-3, 8, -3, 8, -1, "minecraft:grass_block")
for y = 0, 1 do M.setBlock(1, y, 0, "minecraft:stone") end
M.replyQueue = { "ok run my_trees\ngoto 2 0 3 2\nme 0 0 0" }
M.stopAfterRun = true
local okT = M.runMain(SRC.agent_live)
local tx, ty, tz = M.turtle()
check(not okT and M.shellRuns[1] == "carve my_trees" and tx == 2 and ty == 0 and tz == 3, "agent walks to the site first (" .. tx .. "," .. ty .. "," .. tz .. ") and then starts the program")
check(#M.errors == 0 and not M.digs, "it climbed over the wall without digging")

-- every job places its own chests when it is handed some
field(2, 2, 4)
M.setBlock(0, 0, -1, nil)
M.addItem("minecraft:chest", 1)
M.addItem("minecraft:bone_meal", 40)
local okTc = M.runMain(SRC.tree_one)
check(okTc and M.block(0, 0, -1) and M.block(0, 0, -1).name == "minecraft:chest" and M.chestCount(0, 0, -1, "minecraft:oak_log") > 0,
      "tree farm: places its own chest from the inventory and fills it with logs")
mineWorld()
M.setBlock(0, 0, -1, nil)
M.addItem("minecraft:chest", 1)
local okMc = M.runMain(SRC.miner)
check(okMc and M.block(0, 0, -1) and M.block(0, 0, -1).name == "minecraft:chest" and M.chestCount(0, 0, -1, "minecraft:diamond") == 2, "miner: places its own chest too")
M.reset({ fuel = 100, items = { { 1, "minecraft:chest", 2 }, { 2, "minecraft:oak_planks", 3 } } })
local okCc = M.runMain(SRC.craft_sticks)
check(M.block(0, 0, -1) and M.block(-1, 0, 0) and M.block(-1, 0, 0).name == "minecraft:chest", "crafter: places its input and output chests")
-- smelter: logs as the farmed item, charcoal as its own fuel

------------------------------------------------------------- hauler
local function haulWorld()
  M.reset({ fuel = 800 })
  M.floor(-3, 14, -4, 8, -1, "minecraft:grass_block")
  M.setBlock(0, 0, -1, "minecraft:chest", { { "minecraft:oak_log", 40 }, { "minecraft:oak_sapling", 5 }, { "minecraft:stick", 3 } })
  M.setBlock(10, 0, 5, "minecraft:chest", {})
  M.routeText = "leg 1 0 1 -1 10 1 5"                      -- stand above each chest, in the hauler's own frame
end
haulWorld()
local okH, errH = M.runMain(SRC.hauler)
check(okH, "hauler runs its rounds: " .. tostring(errH))
check(M.chestCount(10, 0, 5, "minecraft:oak_log") == 40, "hauler moves all the logs to the other chest (" .. M.chestCount(10, 0, 5, "minecraft:oak_log") .. ")")
check(M.chestCount(0, 0, -1, "minecraft:oak_log") == 0 and M.chestCount(0, 0, -1, "minecraft:oak_sapling") == 5 and M.chestCount(0, 0, -1, "minecraft:stick") == 3,
      "what does not match the filter goes straight back into the source chest")
check(M.chestCount(10, 0, 5, "minecraft:oak_sapling") == 0, "and never reaches the destination")
check(not M.digs and #M.errors == 0, "hauler never digs")
local hx, hy, hz = M.turtle()
check(hx == 10 and hy == 1 and hz == 5, "it ends standing on the drop-off chest (" .. hx .. "," .. hy .. "," .. hz .. ")")
haulWorld()
for y = 0, 1 do M.setBlock(5, y, 0, "minecraft:stone") end              -- a wall across the way
local okW = M.runMain(SRC.hauler)
check(okW and M.chestCount(10, 0, 5, "minecraft:oak_log") == 40 and not M.digs, "hauler climbs over a wall in its way")
haulWorld()
M.routeText = "leg 1 ? no job called 'My Trees' has reported in"
local okE = M.runMain(SRC.hauler)
check(okE and M.chestCount(0, 0, -1, "minecraft:oak_log") == 40 and atHome(), "a leg the app cannot resolve is skipped, nothing moves")
haulWorld()
local okO = M.runMain(SRC.hauler_off)
check(okO and M.chestCount(0, 0, -1, "minecraft:oak_log") == 40, "without live reporting the hauler says so and does nothing")

------------------------------------------------------------- foreman
M.reset({ fuel = 800, items = { { 1, "minecraft:chest", 2 }, { 2, "minecraft:furnace", 1 } } })
M.floor(-4, 6, -4, 14, -1, "minecraft:grass_block")
M.setBlock(0, 0, -3, "minecraft:dirt")
M.setupReplies = { "chest Tree farm 0 1 -3\nfurnace Smelter 2 1 4\nchest Smelter 3 1 4\nskip Keeper no start position yet",
                   "sent Tree farm 2\nfail Smelter no idle agent" }
M.abortAfter(20000)
local okF, errF = M.runMain(SRC.foreman)
check(M.block(0, 0, -3) and M.block(0, 0, -3).name == "minecraft:chest", "foreman digs out the dirt and places the chest at the given cell")
check(M.block(2, 0, 4) and M.block(2, 0, 4).name == "minecraft:furnace", "and a furnace where the plan says")
check(M.block(3, 0, 4) and M.block(3, 0, 4).name == "minecraft:chest", "and the second chest")
check(M.invCount("minecraft:chest") == 0 and M.invCount("minecraft:furnace") == 0, "all the chests and furnaces were used")
local plans, dispatches = 0, 0
for _, p in ipairs(M.posts) do
  if p.url:find("/setup$") then
    if p.body:find('"action":"plan"', 1, true) then plans = plans + 1 end
    if p.body:find('"action":"dispatch"', 1, true) then dispatches = dispatches + 1 end
  end
end
check(plans == 1 and dispatches == 1, "it asks for the plan once and then asks the app to send the jobs out (" .. plans .. "/" .. dispatches .. ")")
local mapPosts, mapAir, mapDirt = 0, false, false
for _, p in ipairs(M.posts) do
  if p.url:find("/map$") then
    mapPosts = mapPosts + 1
    if p.body:find('"air"', 1, true) then mapAir = true end
    if p.body:find('minecraft:dirt', 1, true) or p.body:find('minecraft:grass_block', 1, true) then mapDirt = true end
  end
end
check(mapPosts >= 1 and mapAir and mapDirt, "every program shares what it sees on its way to the map (" .. mapPosts .. " posts)")
local actSeen, faceSeen = false, false
for _, p in ipairs(M.posts) do
  if p.url:find("/status$") then
    if p.body:find('"act":"[^"]', 1) then actSeen = true end
    if p.body:find('"f":%d') then faceSeen = true end
  end
end
check(actSeen and faceSeen, "status reports say what the turtle is trying to do and which way it faces")
check(#M.errors == 0, "no errors from the foreman")

------------------------------------------------------------- foreman: builds turtles
local FRECIPES = {
  { grid = { "oak_log", "-", "-", "-", "-", "-", "-", "-", "-" }, out = "oak_planks", count = 4 },
  { grid = { "oak_planks", "-", "-", "oak_planks", "-", "-", "-", "-", "-" }, out = "stick", count = 4 },
  { grid = { "oak_planks", "oak_planks", "oak_planks", "oak_planks", "-", "oak_planks", "oak_planks", "oak_planks", "oak_planks" }, out = "chest", count = 1 },
  { grid = { "glass", "glass", "glass", "glass", "glass", "glass", "-", "-", "-" }, out = "glass_pane", count = 16 },
  { grid = { "stone", "stone", "stone", "stone", "redstone", "stone", "stone", "glass_pane", "stone" }, out = "computercraft:computer_normal", count = 1 },
  { grid = { "iron_ingot", "iron_ingot", "iron_ingot", "iron_ingot", "computercraft:computer_normal", "iron_ingot", "iron_ingot", "chest", "iron_ingot" }, out = "computercraft:turtle_normal", count = 1 },
  { grid = { "diamond", "diamond", "diamond", "-", "stick", "-", "-", "stick", "-" }, out = "diamond_pickaxe", count = 1 },
  { grid = { "diamond_pickaxe", "computercraft:turtle_normal", "-", "-", "-", "-", "-", "-", "-" }, out = "computercraft:turtle_normal", count = 1 },
  { grid = { "oak_planks", "oak_planks", "-", "oak_planks", "oak_planks", "-", "-", "-", "-" }, out = "crafting_table", count = 1 },
  { grid = { "crafting_table", "computercraft:turtle_normal", "-", "-", "-", "-", "-", "-", "-" }, out = "computercraft:turtle_normal", count = 1 },
  { grid = { "stone", "stone", "stone", "stone", "redstone", "stone", "stone", "redstone", "stone" }, out = "computercraft:disk_drive", count = 1 },
  { grid = { "sugar_cane", "sugar_cane", "sugar_cane", "-", "-", "-", "-", "-", "-" }, out = "paper", count = 3 },
  { grid = { "iron_ingot", "-", "iron_ingot", "iron_ingot", "chest", "iron_ingot", "-", "iron_ingot", "-" }, out = "hopper", count = 1 },
  { grid = { "stone", "stone", "stone", "stone", "redstone", "stone", "stone", "stone", "stone" }, out = "computercraft:wired_modem", count = 1 },   -- the look-alike that wasted the real run
  { grid = { "cobblestone", "cobblestone", "cobblestone", "cobblestone", "-", "cobblestone", "cobblestone", "cobblestone", "cobblestone" }, out = "furnace", count = 1 },
  { grid = { "redstone", "paper", "-", "-", "-", "-", "-", "-", "-" }, out = "computercraft:disk", count = 1 },
}
M.reset({ fuel = 800, recipes = FRECIPES, items = { { 1, "minecraft:coal", 6 } } })
M.floor(-4, 6, -4, 14, -1, "minecraft:grass_block")
M.setBlock(0, 0, -1, "minecraft:chest", { { "minecraft:cobblestone", 20 }, { "minecraft:oak_log", 60 }, { "minecraft:iron_ingot", 60 }, { "minecraft:stone", 40 },
  { "minecraft:redstone", 10 }, { "minecraft:glass", 12 }, { "minecraft:diamond", 12 }, { "minecraft:sugar_cane", 6 }, { "minecraft:coal", 40 },
  { "minecraft:oak_sapling", 8 } })
M.setBlock(-1, 0, 0, "minecraft:chest", {})
local kits, spawns, dispatches = {}, {}, 0
M.setupHandler = function(body)
  if body:find('"action":"spawn"', 1, true) then
    spawns[#spawns + 1] = body:match('"turtle":(%d+)')
    return "ok"
  elseif body:find('"action":"ready"', 1, true) then
    return "ready"
  elseif body:find('"action":"dispatch"', 1, true) then
    dispatches = dispatches + 1
    local tb = M.block(0, 0, 1)
    kits[#kits + 1] = { sap = M.chestCount(0, 0, 2, "minecraft:oak_sapling"), chest = M.chestCount(0, 0, 2, "minecraft:chest"), coal = M.chestCount(0, 0, 2, "minecraft:coal") }
    M.removeBlock(0, 0, 1)                                    -- the new turtle walks off
    return "sent " .. (body:match('"name":"([^"]*)"') or "?") .. " " .. tostring(tb and tb.id)
  end
  return "ok"
end
local setupH = M.setupHandler
M.abortAfter(60000)
M.strictCraft = true
local okB, errB = M.runMain(SRC.foreman_build)
M.strictCraft = nil
check(okB and #M.errors == 0, "foreman builds turtles without errors: " .. tostring(errB) .. " " .. table.concat(M.errors, "; "))
check((M.booted or 0) == 2 and #spawns == 2 and dispatches == 2, "two turtles were started, reported to the app and sent out (" .. tostring(M.booted) .. "/" .. #spawns .. "/" .. dispatches .. ")")
check(kits[1] and kits[1].sap == 4 and kits[1].chest == 1 and kits[1].coal == 16, "the tree farm's turtle got saplings, a chest and coal: " .. tostring(kits[1] and (kits[1].sap .. "/" .. kits[1].chest .. "/" .. kits[1].coal)))
check(kits[2] and kits[2].chest == 2 and kits[2].sap == 0, "the compressor's turtle got 2 chests")
local dr = M.block(0, 1, 1)
check(dr and dr.drive and dr.disk, "the disk drive and its floppy stay in place for the next run")
local startup = M.files["disk/startup.lua"] or ""
check(startup:find("https://raw.example/agent.lua", 1, true) and startup:find("https://raw.example/carve.lua", 1, true), "the floppy's startup downloads the agent and the carve menu")
local dleft = M.chestCount(0, 0, -1, "minecraft:diamond") + M.chestCount(-1, 0, 0, "minecraft:diamond") + M.invCount("minecraft:diamond")
check(dleft == 12 - 6, "each turtle took 3 diamonds for its pickaxe (" .. dleft .. " left)")
check(M.block(0, 0, -1) and M.block(-1, 0, 0), "both chests are still there")
local invSeen, qNow = false, false
for _, p in ipairs(M.posts) do
  if p.url:find("/status$") then
    if p.body:find('"inv":%[%[') then invSeen = true end
    if p.body:find('"t":"Turtle for ', 1, true) then qNow = true end
  end
end
check(invSeen and qNow, "the foreman's status carries its inventory and and the turtles still to build (" .. tostring(invSeen) .. "/" .. tostring(qNow) .. ")")
local stoPosts, stoDiamond = 0, false
for _, p in ipairs(M.posts) do
  if p.url:find("/storage$") then
    stoPosts = stoPosts + 1
    if p.body:find('"minecraft:diamond":', 1, true) and p.body:find("chests", 1, true) then stoDiamond = true end
  end
end
check(stoPosts >= 1 and stoDiamond, "the foreman reports what its chests hold to the Storage tab (" .. stoPosts .. " reports)")

-- the shopping list is enough: the whole default colony (5 turtles, 1 crafty) from exactly the listed materials, crafting as strictly as the real pack
do
  local NAMES = { ["iron ingots"] = "minecraft:iron_ingot", stone = "minecraft:stone", redstone = "minecraft:redstone", diamonds = "minecraft:diamond",
    glass = "minecraft:glass", logs = "minecraft:oak_log", ["sugar cane"] = "minecraft:sugar_cane", cobblestone = "minecraft:cobblestone",
    coal = "minecraft:coal", saplings = "minecraft:oak_sapling", ["bone meal"] = "minecraft:bone_meal" }
  local stacks, listed = {}, {}
  for key, val in SRC.full_materials:gmatch('"([^"]+)": (%d+)') do
    local left, name = tonumber(val), NAMES[key]
    listed[#listed + 1] = key .. "=" .. val
    while left > 0 do
      local c = math.min(64, left); stacks[#stacks + 1] = { name, c }; left = left - c
    end
  end
  M.reset({ fuel = 4000, recipes = FRECIPES, items = { { 1, "minecraft:coal", 6 } } })
  M.floor(-4, 6, -4, 14, -1, "minecraft:grass_block")
  M.setBlock(0, 0, -1, "minecraft:chest", stacks)
  M.setBlock(-1, 0, 0, "minecraft:chest", {})
  spawns, dispatches = {}, 0
  M.setupHandler = setupH
  M.abortAfter(900000)
  M.strictCraft = true
  local okF, errF = M.runMain(SRC.foreman_full)
  M.strictCraft = nil
  local left = {}
  for _, nm in ipairs({ "iron_ingot", "stone", "redstone", "diamond", "glass", "glass_pane", "oak_log", "oak_planks", "stick", "sugar_cane", "paper", "cobblestone", "coal", "chest", "crafting_table", "furnace", "computercraft:computer_normal" }) do
    local full = nm:find(":", 1, true) and nm or ("minecraft:" .. nm)
    local c = M.chestCount(0, 0, -1, full) + M.chestCount(-1, 0, 0, full) + M.invCount(full)
    if c > 0 then left[#left + 1] = nm .. "=" .. c end
  end
  check(okF and #M.errors == 0 and #spawns == 5 and dispatches == 5,
    "the shopping list (" .. table.concat(listed, ", ") .. ") is enough to build all five turtles: " .. #spawns .. " started, " .. dispatches .. " sent, "
    .. tostring(errF) .. " " .. table.concat(M.errors, "; ") .. " | left: " .. table.concat(left, " ") .. " | " .. table.concat({ M.screen[1] or "", M.screen[2] or "", M.screen[3] or "", M.screen[4] or "", M.screen[5] or "", M.screen[6] or "" }, " / "))
end

-- a pack where the disk drive does not take items from a turtle's drop: the floppy lands on the ground, the foreman crafts another and right-clicks with it
do
  M.reset({ fuel = 800, recipes = FRECIPES, items = { { 1, "minecraft:coal", 6 } } })
  M.floor(-4, 6, -4, 14, -1, "minecraft:grass_block")
  M.setBlock(0, 0, -1, "minecraft:chest", { { "minecraft:cobblestone", 20 }, { "minecraft:oak_log", 60 }, { "minecraft:iron_ingot", 60 }, { "minecraft:stone", 40 },
    { "minecraft:redstone", 14 }, { "minecraft:glass", 12 }, { "minecraft:diamond", 12 }, { "minecraft:sugar_cane", 6 }, { "minecraft:coal", 40 },
    { "minecraft:oak_sapling", 8 } })
  M.setBlock(-1, 0, 0, "minecraft:chest", {})
  spawns, dispatches = {}, 0
  M.setupHandler = setupH
  M.abortAfter(300000)
  M.driveNoDrop = true
  M.strictCraft = true
  local okD, errD = M.runMain(SRC.foreman_build)
  M.driveNoDrop, M.strictCraft = nil, nil
  check(okD and #M.errors == 0 and #spawns == 2,
    "when the drive does not take a dropped floppy the foreman right-clicks the drive with one: " .. #spawns .. " started, " .. tostring(errD) .. " " .. table.concat(M.errors, "; ") .. " | " .. table.concat({ M.screen[1] or "", M.screen[2] or "", M.screen[3] or "", M.screen[4] or "", M.screen[5] or "" }, " / "))
end

-- a drive that only takes a floppy from above (like a hopper): the foreman climbs over it and drops it down
do
  M.reset({ fuel = 800, recipes = FRECIPES, items = { { 1, "minecraft:coal", 6 } } })
  M.floor(-4, 6, -4, 14, -1, "minecraft:grass_block")
  M.setBlock(0, 0, -1, "minecraft:chest", { { "minecraft:cobblestone", 20 }, { "minecraft:oak_log", 60 }, { "minecraft:iron_ingot", 60 }, { "minecraft:stone", 40 },
    { "minecraft:redstone", 14 }, { "minecraft:glass", 12 }, { "minecraft:diamond", 12 }, { "minecraft:sugar_cane", 6 }, { "minecraft:coal", 40 },
    { "minecraft:oak_sapling", 8 } })
  M.setBlock(-1, 0, 0, "minecraft:chest", {})
  spawns, dispatches = {}, 0
  M.setupHandler = setupH
  M.abortAfter(300000)
  M.driveTopOnly = true
  M.strictCraft = true
  local okT, errT = M.runMain(SRC.foreman_build)
  M.driveTopOnly, M.strictCraft = nil, nil
  check(okT and #M.errors == 0 and #spawns == 2, "a drive that only takes a floppy from above still gets loaded: " .. #spawns .. " started, " .. tostring(errT) .. " " .. table.concat(M.errors, "; "))
end
-- a second run finds the drive and floppy still standing and does not build another
do
  local dr0 = M.block(0, 1, 1)
  M.reset({ fuel = 800, recipes = FRECIPES, items = { { 1, "minecraft:coal", 6 } } })
  M.floor(-4, 6, -4, 14, -1, "minecraft:grass_block")
  M.setBlock(0, 1, 1, "minecraft:disk_drive_placeholder")
  M.setBlock(0, 1, 1, "computercraft:disk_drive", nil)
  local b = M.block(0, 1, 1); b.drive = true; b.disk = "computercraft:disk"
  M.setBlock(0, 0, -1, "minecraft:chest", { { "minecraft:cobblestone", 20 }, { "minecraft:oak_log", 60 }, { "minecraft:iron_ingot", 60 }, { "minecraft:stone", 21 },
    { "minecraft:redstone", 3 }, { "minecraft:glass", 12 }, { "minecraft:diamond", 12 }, { "minecraft:coal", 40 }, { "minecraft:oak_sapling", 8 } })
  M.setBlock(-1, 0, 0, "minecraft:chest", {})
  spawns, dispatches = {}, 0
  M.setupHandler = setupH
  M.abortAfter(300000)
  M.strictCraft = true
  local okR, errR = M.runMain(SRC.foreman_build)
  M.strictCraft = nil
  check(okR and #M.errors == 0 and #spawns == 2, "with the drive and floppy already there it needs no drive, floppy, paper or sugar cane: " .. #spawns .. " started, " .. tostring(errR) .. " " .. table.concat(M.errors, "; "))
end

-- almost out of fuel with no coal in its own inventory: it eats some of the chest's coal first and keeps the rest in the chest
do
  M.reset({ fuel = 20, recipes = FRECIPES, items = {} })
  M.floor(-4, 6, -4, 14, -1, "minecraft:grass_block")
  M.setBlock(0, 0, -1, "minecraft:chest", { { "minecraft:coal", 40 }, { "minecraft:oak_log", 10 } })
  M.setBlock(-1, 0, 0, "minecraft:chest", {})
  spawns, dispatches = {}, 0
  M.setupHandler = setupH
  M.abortAfter(120)
  pcall(M.runMain, SRC.foreman_build)
  local lvl = turtle.getFuelLevel()
  check(lvl > 500 and M.chestCount(0, 0, -1, "minecraft:coal") + M.chestCount(-1, 0, 0, "minecraft:coal") + M.invCount("minecraft:coal") >= 25,
    "the foreman refuels from the chest first and keeps the surplus coal (fuel " .. tostring(lvl) .. ")")
end

-- a plain turtle (no crafting table equipped): it says so, and equips a crafting table from its inventory
M.reset({ fuel = 800, recipes = FRECIPES, items = { { 1, "minecraft:coal", 6 } } })
M.makePlain()
M.setBlock(0, 0, -1, "minecraft:chest", {}); M.setBlock(-1, 0, 0, "minecraft:chest", {})
local okP, errP = M.runMain(SRC.foreman_build)
check(okP and not M.equipped and #M.errors == 0, "a plain turtle without a crafting table stops with a plain message instead of crashing: " .. tostring(errP))
M.reset({ fuel = 800, recipes = FRECIPES, items = { { 1, "minecraft:coal", 6 }, { 2, "minecraft:crafting_table", 1 } } })
M.makePlain()
M.setBlock(0, 0, -1, "minecraft:chest", {}); M.setBlock(-1, 0, 0, "minecraft:chest", {})
M.abortAfter(400)
pcall(M.runMain, SRC.foreman_build)
check(M.equipped, "with a crafting table in its inventory it equips it and becomes crafty")
-- versions where the crafting table only appears as a "workbench" peripheral
M.reset({ fuel = 800, recipes = FRECIPES, items = { { 1, "minecraft:coal", 6 }, { 2, "minecraft:crafting_table", 1 } } })
M.makePlain(); M.workbenchOnly = true
M.setBlock(0, 0, -1, "minecraft:chest", {}); M.setBlock(-1, 0, 0, "minecraft:chest", {})
M.abortAfter(400)
pcall(M.runMain, SRC.foreman_build)
check(M.equipped and M.workbenchSide == "right", "it also copes when the crafting table only shows up as a workbench peripheral")
M.workbenchOnly = false
M.makeCrafty()
M.makeCrafty()

------------------------------------------------------------- storage keeper
local function keeperWorld(noPeriph)
  M.reset({ fuel = 800, items = { { 1, "minecraft:chest", 8 } } })
  M.floor(-4, 6, -4, 14, -1, "minecraft:grass_block")
  M.setBlock(0, 0, -1, "minecraft:chest", { { "minecraft:oak_log", 30 }, { "minecraft:cobblestone", 20 }, { "minecraft:oak_sapling", 10 } })
  M.noPeripheral = noPeriph
end
local function lastBody(pat)
  for i = #M.posts, 1, -1 do
    if M.posts[i].url:find(pat) then return M.posts[i].body end
  end
end
keeperWorld()
M.abortAfter(1500)
local okK, errK = M.runMain(SRC.keeper)
check(M.block(0, 0, -1) and M.block(-1, 0, 0) and M.block(-1, 0, 0).name == "minecraft:chest", "keeper places its own pickup chest on the left (drop chest was there)")
check(M.chestCount(1, 0, 1, "minecraft:oak_log") == 30, "first kind of item gets the first storage chest (" .. M.chestCount(1, 0, 1, "minecraft:oak_log") .. ")")
check(M.chestCount(-1, 0, 1, "minecraft:cobblestone") == 20, "a new kind of item gets a chest of its own")
check(M.chestCount(0, 1, 1, "minecraft:oak_sapling") == 10, "chests also go above the corridor")
check(M.chestCount(0, 0, -1) == 0, "the drop chest is emptied")
check(M.invCount("minecraft:oak_log") == 0 and M.invCount("minecraft:cobblestone") == 0, "nothing is left in the keeper's inventory")
check(M.invCount("minecraft:chest") == 8 - 1 - 4, "it used 1 chest for the pickup and 4 for storage, one of them a spare (" .. tostring(M.invCount("minecraft:chest")) .. " left)")
local body = lastBody("/storage$")
check(body and body:find('"minecraft:oak_log":30', 1, true) and body:find('"minecraft:cobblestone":20', 1, true) and body:find('"chests":4', 1, true),
      "it reports the list of everything to the app: " .. tostring(body))
check(M.digs == 1 and M.invCount("minecraft:dirt") == 0 and #M.errors == 0, "the only digging is the ground for the chest below, and the dirt is thrown away")

keeperWorld()
M.storageReplies = { "order 20 minecraft:oak_log" }
M.abortAfter(2500)
M.runMain(SRC.keeper)
check(M.chestCount(-1, 0, 0, "minecraft:oak_log") == 20, "an order from the web page ends up in the pickup chest (" .. M.chestCount(-1, 0, 0, "minecraft:oak_log") .. ")")
check(M.chestCount(1, 0, 1, "minecraft:oak_log") == 10, "and leaves the rest in storage")
body = lastBody("/storage$")
check(body and body:find('"minecraft:oak_log":10', 1, true), "the list is updated afterwards: " .. tostring(body))

keeperWorld(true)
M.storageReplies = { "order 15 minecraft:cobblestone" }
M.abortAfter(2500)
M.runMain(SRC.keeper)
check(M.chestCount(-1, 0, 0, "minecraft:cobblestone") == 15 and M.chestCount(-1, 0, 1, "minecraft:cobblestone") == 5, "works without the peripheral API too (remembers by itself)")
body = lastBody("/storage$")
check(body and body:find('"minecraft:cobblestone":5', 1, true) and body:find('"minecraft:oak_log":30', 1, true), "the list stays right without peeking: " .. tostring(body))

keeperWorld()
M.storageReplies = { "order 99 minecraft:oak_log", "order 5 minecraft:diamond" }
M.abortAfter(2500)
M.runMain(SRC.keeper)
check(M.chestCount(-1, 0, 0, "minecraft:oak_log") == 30 and M.invCount("minecraft:diamond") == 0, "asking for more than there is delivers what exists; unknown items do nothing")
keeperWorld()
M.floor(-4, 6, -4, 14, -1, "minecraft:grass_block")
for z = 1, 3 do M.setBlock(1, 0, z, "minecraft:stone") end                      -- rock where the first chest goes
M.abortAfter(1200)
M.runMain(SRC.keeper)
check(M.chestCount(1, 0, 1, "minecraft:oak_log") == 30 and M.invCount("minecraft:stone") == 0 and M.invCount("minecraft:cobblestone") == 0, "it digs out a spot for a chest and throws the rubble away")

-- a turtle without a label takes the name the app gives it
keeperWorld()
M.label = nil
M.abortAfter(40)
M.runMain(SRC.keeper)
check(M.label == "Infernus", "an unlabelled turtle names itself after a Deadlock hero, by its id, on startup (" .. tostring(M.label) .. ")")
keeperWorld()
M.label = "Mine"
M.replyQueue = { "ok\nlabel Juno" }
M.abortAfter(40)
M.runMain(SRC.keeper)
check(M.label == "Mine", "a turtle that already has a label keeps it")
M.label = "Lumber Jack"

-- a turtle names itself on its first start when the program carries a name
keeperWorld()
M.label = nil
M.abortAfter(5)
M.runMain(SRC.keeper_named)
check(M.label == "Jupiter", "a program with a turtle name sets the label on start, even with no connection to the app (" .. tostring(M.label) .. ")")
keeperWorld()
M.label = "Mine"
M.abortAfter(5)
M.runMain(SRC.keeper_named)
check(M.label == "Mine", "but never replaces a label the turtle already has")
M.label = "Lumber Jack"

-- when the app can't be reached the screen says why, and the turtle keeps trying
keeperWorld()
M.httpDown = true
M.abortAfter(400)
M.runMain(SRC.keeper)
check((M.screen[13] or ""):find("NOT reaching", 1, true) ~= nil, "the turtle's screen shows why it can't reach the app: " .. tostring(M.screen[13]))
local failedPosts = #M.posts
keeperWorld()
M.httpDown = true
M.abortAfter(300)
M.runMain(SRC.keeper)
M.httpDown = false
M.abortAfter(300)
M.runMain(SRC.keeper, "resume")
check(#M.posts > 0, "it reports again once the app is up (no giving up for good after 5 failures)")
keeperWorld()
M.abortAfter(30)
M.runMain(SRC.hauler_off)
check((M.screen[13] or ""):find("OFF", 1, true) ~= nil, "a program uploaded without live reporting says so on screen: " .. tostring(M.screen[13]))

return R
