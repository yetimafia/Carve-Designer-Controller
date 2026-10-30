-- Carve miner: goes underground and looks for resources (coal, iron, copper, gold, redstone, lapis, diamond, emerald).
-- It digs a shaft straight down from the START cell, then a tunnel (the spine) and side tunnels (ribs) every 3 blocks,
-- checks every wall it passes, and mines any wanted ore it sees (following the whole vein). When its inventory is
-- full it climbs back, empties itself into the chest BEHIND the start, and returns. Coal it finds refuels it.
-- Stand on the START cell facing forward (+z); put a chest right behind you; give it some coal to start.
-- Run again with  stop  to cancel the automatic restart.

local args = { ... }

--@@PLAN@@

local STATE_FILE = "carve.miner"
local PROG_FILE = "carve.minerprog"
local TITLE = PLAN.name or "Miner"
local FUEL_HINT = "coal"
local BURN = { "coal", "charcoal" }

--@@COMMON@@

local DEPTH, REACH, RIB = PLAN.depth, PLAN.reach, PLAN.rib
local OPP = { 3, 4, 1, 2, 6, 5 }
local JUNK = { "cobblestone", "cobbled_deepslate", "dirt", "gravel", "andesite", "diorite", "granite", "tuff",
               "netherrack", "sand", "stone", "deepslate", "calcite", "dripstone" }
local found, nribs = 0, 0
local spineLen, ribsDone = 0, 0
local outbox, lastFlush = {}, 0

local function wanted(name)
  if not name or not name:find("_ore", 1, true) then return false end
  for _, w in ipairs(PLAN.want) do
    if name:find(w, 1, true) then return true end
  end
  return false
end

local function liquid(name)
  return name ~= nil and (name:find("lava", 1, true) ~= nil or name:find("water", 1, true) ~= nil)
end

local function flush(force)
  if not fleet.on then outbox = {}; return end
  if #outbox == 0 or (not force and #outbox < 20 and os.clock() - lastFlush < 60) then return end
  lastFlush = os.clock()
  local parts = {}
  for _, c in ipairs(outbox) do
    parts[#parts + 1] = "[" .. c[1] .. "," .. c[2] .. "," .. c[3] .. "," .. jq(c[4]) .. "]"
  end
  outbox = {}
  pcall(http.post, { url = LIVE_URL .. "/map", timeout = 5, headers = { ["Content-Type"] = "application/json" },
    body = '{"v":1,"id":' .. os.getComputerID() .. ',"cells":[' .. table.concat(parts, ",") .. "]}" })
end

local function inspectDir(d)
  local ok, data
  if d == 5 then ok, data = turtle.inspectUp()
  elseif d == 6 then ok, data = turtle.inspectDown()
  else turnTo(d); ok, data = turtle.inspect() end
  if not ok then return nil end
  return type(data) == "table" and (data.name or "?") or "?"
end

local function digDir(d)
  if d == 5 then return turtle.digUp() elseif d == 6 then return turtle.digDown() end
  turnTo(d)
  return turtle.dig()
end

-- throw away stone and dirt when the inventory is getting full
local function dropJunk()
  for s = 1, 16 do
    local n = itemName(s)
    if n then
      for _, j in ipairs(JUNK) do
        if n == "minecraft:" .. j then
          turtle.select(s)
          turtle.dropDown()
          break
        end
      end
    end
  end
  turtle.select(1)
end

-- empty the inventory into the chest behind the start, then come back to where we were
local function unloadTrip()
  local bx, by, bz = pos.x, pos.y, pos.z
  goTo(0, by, 0, "zx")
  goTo(0, 0, 0, "y")
  burn(1500)
  turnTo(3)
  while true do
    dumpFront()
    if freeSlots() >= 14 then break end
    say(TITLE, "", "The chest behind me is full.", "Empty it. Waiting...")
    sleep(10)
  end
  turnTo(1)
  fleet.msg = "Unloaded"
  goTo(0, by, 0, "y")
  goTo(bx, by, bz, "xz")
end

local function checkSpace()
  if freeSlots() <= 4 then dropJunk() end
  if freeSlots() <= 2 then unloadTrip() end
end

-- mine the ore I am looking at and everything of the same kind touching it
local function vein(budget)
  local order = { 5, 6, face, face % 4 + 1, (face + 1) % 4 + 1, (face + 2) % 4 + 1 }
  for _, d in ipairs(order) do
    if budget <= 0 then break end
    local name = inspectDir(d)
    if wanted(name) then
      outbox[#outbox + 1] = { pos.x + DX[d], pos.y + DY[d], pos.z + DZ[d], name }
      digDir(d)
      found = found + 1
      fleet.n = found
      step(d)
      budget = vein(budget - 1)
      step(OPP[d])
    end
  end
  return budget
end

local function lookAround()
  vein(40)
  checkSpace()
end

-- dig one cell along direction d and step into it; false when something stops us (liquid, bedrock)
local function tunnelStep(d)
  local name = inspectDir(d)
  if liquid(name) or name == "minecraft:bedrock" then return false end
  step(d)
  return true
end

local function saveProgress()
  writeFile(PROG_FILE, ribsDone .. "," .. spineLen)
end

local function loadProgress()
  local s = readFile(PROG_FILE)
  local a, b = (s or ""):match("^(%d+),(%d+)")
  if a then ribsDone, spineLen = tonumber(a), tonumber(b) end
end

local function status(what)
  fleet.total = nribs
  say(TITLE, "", what, "Rib " .. ribsDone .. "/" .. nribs .. "  ores found " .. found,
      "At " .. pos.x .. " " .. pos.y .. " " .. pos.z)
end

-- dig the shaft straight down from the start
local function shaft()
  while pos.y > -DEPTH do
    if not tunnelStep(6) then break end
    lookAround()
    if pos.y % 5 == 0 then status("Going down...") end
  end
end

-- extend the main tunnel (east) up to x, looking at the walls as it goes
local function spineTo(x)
  goTo(spineLen, -DEPTH, 0, "yxz")
  while spineLen < x do
    if not tunnelStep(2) then spineLen = x; break end     -- blocked: ribs beyond are skipped
    spineLen = spineLen + 1
    lookAround()
  end
  saveProgress()
end

local function rib(k)
  local i, side = math.ceil(k / 2), (k % 2 == 1) and 1 or -1
  local x = 3 * i
  spineTo(x)
  goTo(x, -DEPTH, 0, "yxz")
  local d = side > 0 and 1 or 3
  for _ = 1, RIB do
    if not tunnelStep(d) then break end
    lookAround()
  end
  goTo(x, -DEPTH, 0, "z")
  ribsDone = k
  saveProgress()
  flush(true)
  status("Mining...")
end

local function main()
  if not turtle then printError("This program must run on a turtle."); return end
  if args[1] == "stop" then
    removeStartup(); fs.delete(STATE_FILE); fs.delete(PROG_FILE)
    finish(TITLE, "", "Stopped. The automatic restart is removed.")
    return
  end
  nribs = math.floor(REACH / 3) * 2
  if RIB == 0 then nribs = 0 end
  if args[1] == "resume" and loadPos() then
    say(TITLE, "", "Resuming after a restart...")
    loadProgress()
    goTo(0, pos.y, 0, "zx")                               -- back along the tunnels to the shaft
    goTo(0, 0, 0, "y")
  else
    fs.delete(STATE_FILE); fs.delete(PROG_FILE)
    pos.x, pos.y, pos.z, face = 0, 0, 0, 1
    savePos()
  end
  installStartup()
  ensureChest(3, "finds"); turnTo(1)
  shaft()
  if RIB == 0 then
    spineTo(REACH)
  else
    for k = ribsDone + 1, nribs do rib(k) end
    spineTo(REACH)
  end
  flush(true)
  goTo(0, -DEPTH, 0, "zx")
  goTo(0, 0, 0, "y")
  burn(1500)
  turnTo(3)
  dumpFront()
  turnTo(1)
  removeStartup()
  fs.delete(STATE_FILE); fs.delete(PROG_FILE)
  finish(TITLE, "", "Done. " .. found .. " ores mined.", "Everything is in the chest.")
end

if rawget(_G, "CARVE_TEST") then
  return { main = main, pos = pos }
end
runMain(main)
