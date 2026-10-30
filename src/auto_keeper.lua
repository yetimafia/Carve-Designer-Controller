-- Carve storage keeper: a warehouse of chests that builds itself, remembers what is in every chest and
-- reports the list to the Designer app (Storage tab of the Fleet page).
--
--   behind the start : the DROP chest. Anything put in there (by you or by a hauler) is sorted into storage.
--   left of the start: the PICKUP chest. Items you ask for on the web page are put there.
--   in front         : a corridor with up to 4 storage chests per step (right, left, above, below).
--
-- Start it with a chest in the first slot (more chests, fuel in other slots). It places the drop chest, the
-- pickup chest and then one storage chest at a time when it needs room. Chests dropped into the drop chest
-- are kept by the turtle and used to grow the warehouse.
-- Run again with  stop  to cancel the automatic restart;  reset  forgets the list of what is stored.

local args = { ... }

--@@PLAN@@

local STATE_FILE = "carve.keeper"
local INDEX_FILE = "carve.keeperidx"
local TITLE = PLAN.name or "Storage keeper"
local FUEL_HINT = "coal or charcoal"
local BURN = { "coal", "charcoal" }
local KEEP = {}

--@@COMMON@@

local MAXC = PLAN.length * 4            -- most storage chests this warehouse may grow to
local STACKMAX = 64
local built = 0                         -- storage chests placed so far
local idx = {}                          -- idx[k] = { [item name] = count }  for chest k
local full = {}                         -- full[k] = true while chest k refused items
local orders = {}                       -- { { item =, count = } } waiting to be put in the pickup chest
local reported = -100
local hasPeripheral = peripheral ~= nil and peripheral.wrap ~= nil
local dirty = true

local SIDES = {
  { name = "right", face = 2, drop = "drop", suck = "suck", wrap = "front" },
  { name = "left", face = 4, drop = "drop", suck = "suck", wrap = "front" },
  { name = "above", face = nil, drop = "dropUp", suck = "suckUp", wrap = "top" },
  { name = "below", face = nil, drop = "dropDown", suck = "suckDown", wrap = "bottom" },
}

local function cellOf(k) return math.floor((k - 1) / 4) + 1 end
local function sideOf(k) return SIDES[(k - 1) % 4 + 1] end

---------------------------------------------------------------- the list of what is stored
local function saveIndex()
  local out = { "built " .. built }
  for k = 1, built do
    for name, c in pairs(idx[k] or {}) do
      if c > 0 then out[#out + 1] = k .. " " .. c .. " " .. name end
    end
  end
  writeFile(INDEX_FILE, table.concat(out, "\n") .. "\n")
  dirty = true
end

local function loadIndex()
  local s = readFile(INDEX_FILE)
  if not s then return end
  built = 0
  for line in s:gmatch("[^\n]+") do
    local b = line:match("^built (%d+)$")
    if b then
      built = tonumber(b)
      for k = 1, built do idx[k] = idx[k] or {} end
    else
      local k, c, name = line:match("^(%d+) (%d+) (.+)$")
      k = tonumber(k)
      if k and k <= built then idx[k][name] = tonumber(c) end
    end
  end
end

local function totals()
  local t, stacks = {}, 0
  for k = 1, built do
    for name, c in pairs(idx[k] or {}) do
      t[name] = (t[name] or 0) + c
      stacks = stacks + math.ceil(c / STACKMAX)
    end
  end
  return t, stacks
end

local function emptyChests()
  local n = 0
  for k = 1, built do
    if next(idx[k]) == nil and not full[k] then n = n + 1 end
  end
  return n
end

---------------------------------------------------------------- talking to the app
local function chestsHeld()
  local n = 0
  for s = 1, 16 do
    if isChestItem(itemName(s)) then n = n + turtle.getItemCount(s) end
  end
  return n
end

-- send the list, get the orders back ("order <count> <item>" lines)
local function sync(force)
  if not fleet.on then return end
  local now = os.clock()
  if not force and not dirty and now - reported < 20 then return end
  if not force and now - reported < 4 then return end
  reported = now
  local t, stacks = totals()
  local parts = {}
  for name, c in pairs(t) do
    if c > 0 then parts[#parts + 1] = jq(name) .. ":" .. c end
  end
  table.sort(parts)
  local body = '{"v":1,"id":' .. os.getComputerID() .. ',"name":' .. jq(PLAN.name or "") ..
    ',"chests":' .. built .. ',"max":' .. MAXC .. ',"stacks":' .. stacks .. ',"slots":' .. (built * 27) ..
    ',"spare":' .. chestsHeld() .. ',"items":{' .. table.concat(parts, ",") .. "}}"
  local ok, res = pcall(http.post, { url = LIVE_URL .. "/storage", body = body, timeout = 5,
                                     headers = { ["Content-Type"] = "application/json" } })
  if not ok or not res then return end
  dirty = false
  local text = ""
  pcall(function() text = res.readAll() or ""; res.close() end)
  for line in text:gmatch("[^\n]+") do
    local n, item = line:match("^order (%d+) ([%w_:%.%-]+)$")
    if n and #orders < 40 then orders[#orders + 1] = { item = item, count = math.min(tonumber(n), 4096) } end
  end
end

local function status(...)
  fleet.n = built
  fleet.total = MAXC
  say(TITLE, "", ...)
  sync(false)
end

---------------------------------------------------------------- walking the corridor
local function toCell(z)
  if pos.x ~= 0 or pos.y ~= 0 then goTo(0, 0, pos.z, "yx") end
  goTo(0, 0, z, "yzx")
end

-- turn to / get ready for a chest at storage position k (or the special "pickup" / "drop" chests)
local function aim(side)
  if side.face then turnTo(side.face) end
end

local function call(side, which, ...)
  if which == "drop" then return turtle[side.drop](...) end
  return turtle[side.suck](...)
end

-- what the chest in front says it holds (needs the peripheral API); nil when it can't be asked
local function peek(side)
  if not hasPeripheral then return nil end
  local ok, p = pcall(peripheral.wrap, side.wrap)
  if not ok or type(p) ~= "table" or not p.list then return nil end
  local ok2, list = pcall(p.list)
  if not ok2 or type(list) ~= "table" then return nil end
  local out = {}
  for _, st in pairs(list) do
    if st and st.name then out[st.name] = (out[st.name] or 0) + (st.count or 0) end
  end
  return out
end

local function refresh(k, side)
  local now = peek(side)
  if now then idx[k] = now end
end

-- is there already a chest in the cell in front / above / below?
local function chestThere(side)
  local fn = side.drop == "dropUp" and turtle.inspectUp or side.drop == "dropDown" and turtle.inspectDown or turtle.inspect
  local ok, data = fn()
  return ok and isChestItem(type(data) == "table" and data.name or nil)
end

-- dig whatever is in the cell, throwing the rubble away so it doesn't fill my inventory
local function clearCell(side)
  local before = {}
  for s = 1, 16 do before[s] = { itemName(s), turtle.getItemCount(s) } end
  local detect = side.drop == "dropUp" and turtle.detectUp or side.drop == "dropDown" and turtle.detectDown or turtle.detect
  local inspect = side.drop == "dropUp" and turtle.inspectUp or side.drop == "dropDown" and turtle.inspectDown or turtle.inspect
  local dig = side.drop == "dropUp" and turtle.digUp or side.drop == "dropDown" and turtle.digDown or turtle.dig
  if detect() then
    local _, data = inspect()
    if isProtected(data) then return false end
    dig()
  end
  for s = 1, 16 do
    local n = itemName(s)
    local c = turtle.getItemCount(s)
    local b = before[s]
    local added = (b[1] == n or b[1] == nil) and (c - (b[1] == n and b[2] or 0)) or 0
    if n and added > 0 and not isChestItem(n) then
      turtle.select(s)
      turtle[side.drop](added)
    end
  end
  turtle.select(1)
  return true
end

local function placeChest(side)
  for s = 1, 16 do
    if isChestItem(itemName(s)) then
      turtle.select(s)
      local fn = side.drop == "dropUp" and turtle.placeUp or side.drop == "dropDown" and turtle.placeDown or turtle.place
      local ok = fn()
      turtle.select(1)
      return ok
    end
  end
  return false
end

-- build storage chest number built+1 if I have a chest and there is room in the plan
local function buildNext()
  if built >= MAXC or chestsHeld() == 0 then return false end
  local k = built + 1
  toCell(cellOf(k))
  local side = sideOf(k)
  aim(side)
  if not chestThere(side) then
    if not clearCell(side) or not placeChest(side) then return false end
  end
  built = k
  idx[k] = {}
  full[k] = nil
  saveIndex()
  status("Built storage chest " .. built .. " of " .. MAXC)
  return true
end

---------------------------------------------------------------- putting things away
local function dropInto(k, s)
  local side = sideOf(k)
  toCell(cellOf(k))
  aim(side)
  turtle.select(s)
  local name = itemName(s)
  local before = turtle.getItemCount(s)
  local ok = call(side, "drop")
  local moved = before - turtle.getItemCount(s)
  turtle.select(1)
  if moved > 0 then
    idx[k][name] = (idx[k][name] or 0) + moved
  end
  if not ok or turtle.getItemCount(s) > 0 then full[k] = true end
  if hasPeripheral then refresh(k, side) end
  return moved
end

-- phase 1: chests that already hold this item, 2: empty chests, 3: any other chest with room
local function tryChests(s, name, phase)
  for k = 1, built do
    if not full[k] then
      local has = idx[k][name] ~= nil
      local empty = next(idx[k]) == nil
      if (phase == 1 and has) or (phase == 2 and empty) or (phase == 3 and not has and not empty) then
        status("Storing " .. name:gsub("^minecraft:", ""))
        dropInto(k, s)
        if turtle.getItemCount(s) == 0 then return true end
      end
    end
  end
  return false
end

-- put the stack in slot s into storage. false when there is no room (and I couldn't build more)
local function storeSlot(s)
  while turtle.getItemCount(s) > 0 do
    local name = itemName(s)
    if tryChests(s, name, 1) or tryChests(s, name, 2) then break end
    if not buildNext() then                     -- a new kind of item gets its own chest if I can build one
      if tryChests(s, name, 3) then break end
      saveIndex()
      return false
    end
  end
  saveIndex()
  return true
end

-- fuel from what comes in: burn a few coal/charcoal when low
local function topUpFuel(s)
  local n = itemName(s)
  if not n or not (n:find("coal", 1, true) or n:find("charcoal", 1, true)) then return end
  local lvl = turtle.getFuelLevel()
  if lvl ~= "unlimited" and lvl < 1500 then
    turtle.select(s)
    turtle.refuel(math.min(turtle.getItemCount(s), 8))
    turtle.select(1)
  end
end

-- chests are kept to build with (up to 2 stacks); everything else goes into storage
local function storeInventory()
  local keptChests = 0
  local ok = true
  for s = 1, 16 do
    local n = itemName(s)
    if n then
      if isChestItem(n) and keptChests < 2 then
        keptChests = keptChests + 1
      elseif n == "minecraft:furnace" then
        -- never mine
      else
        topUpFuel(s)
        if turtle.getItemCount(s) > 0 and not storeSlot(s) then
          ok = false
        end
      end
    end
  end
  return ok
end

local function intake()
  toCell(0)
  turnTo(3)
  local got = 0
  while turtle.suck() do
    got = got + 1
    if freeSlots() <= 3 then
      storeInventory()
      toCell(0)
      turnTo(3)
    end
    if got > 200 then break end
  end
  turnTo(1)
  return got
end

---------------------------------------------------------------- taking things out
local function countInv(name)
  local c = 0
  for s = 1, 16 do
    if itemName(s) == name then c = c + turtle.getItemCount(s) end
  end
  return c
end

local function takeFromChest(k, name, want)
  local side = sideOf(k)
  toCell(cellOf(k))
  aim(side)
  full[k] = nil
  local before = countInv(name)
  local held = {}
  for s = 1, 16 do held[s] = itemName(s) end
  for _ = 1, 40 do
    if countInv(name) >= want or freeSlots() <= 1 then break end
    if not call(side, "suck") then break end
  end
  -- anything else I pulled out goes straight back
  for s = 1, 16 do
    local n = itemName(s)
    if n and n ~= name and n ~= held[s] and not isChestItem(n) then
      turtle.select(s)
      call(side, "drop")
    end
  end
  turtle.select(1)
  if hasPeripheral and peek(side) then
    refresh(k, side)
  else
    local left = (idx[k][name] or 0) - (countInv(name) - before)
    idx[k][name] = left > 0 and left or nil
  end
end

-- carry what is in my inventory of this item to the pickup chest. Returns how many arrived.
local function deliver(name, want)
  toCell(0)
  turnTo(4)
  local moved = 0
  for s = 1, 16 do
    if itemName(s) == name and moved < want then
      turtle.select(s)
      local before = turtle.getItemCount(s)
      turtle.drop(math.min(before, want - moved))
      moved = moved + before - turtle.getItemCount(s)
    end
  end
  turtle.select(1)
  turnTo(1)
  return moved
end

local function fulfil(order)
  local name, want = order.item, order.count
  status("Fetching " .. want .. " " .. name:gsub("^minecraft:", ""))
  local fetched = 0
  for k = 1, built do
    if (idx[k][name] or 0) > 0 and fetched < want then
      takeFromChest(k, name, want - fetched)
      fetched = countInv(name)
      if freeSlots() <= 1 then break end
    end
  end
  -- never hand out more than asked for: the surplus goes back into storage
  local moved = deliver(name, want)
  if moved == 0 and countInv(name) > 0 then
    status("The pickup chest is full.", "Empty it, then ask again.")
    storeInventory()
    return false
  end
  if countInv(name) > 0 then storeInventory() end
  saveIndex()
  return true
end

---------------------------------------------------------------- full scan of every chest
local function rescan()
  if not hasPeripheral then return end
  for k = 1, built do
    local side = sideOf(k)
    toCell(cellOf(k))
    aim(side)
    refresh(k, side)
    full[k] = nil
  end
  saveIndex()
end

local function main()
  if not turtle then printError("This program must run on a turtle."); return end
  if args[1] == "stop" then
    removeStartup(); fs.delete(STATE_FILE)
    finish(TITLE, "", "Stopped. The automatic restart is removed.")
    return
  end
  if args[1] == "reset" then fs.delete(INDEX_FILE) end
  if args[1] == "resume" and loadPos() then
    say(TITLE, "", "Resuming after a restart...")
  else
    pos.x, pos.y, pos.z, face = 0, 0, 0, 1
    savePos()
  end
  loadIndex()
  installStartup()
  ensureChest(3, "drop chest")
  ensureChest(4, "pickup chest")
  turnTo(1)
  local lastScan = os.clock()
  rescan()
  while true do
    -- 1. things people put in the drop chest
    local got = intake()
    if got > 0 then storeInventory() end
    -- 2. grow when there is no empty chest left for a new kind of item
    if emptyChests() == 0 and built < MAXC and chestsHeld() > 0 then buildNext() end
    -- 3. tell the app, then carry out what it asked for
    sync(true)
    local order = table.remove(orders, 1)
    while order do
      fulfil(order)
      order = table.remove(orders, 1)
      sync(true)
    end
    -- 4. now and then look into every chest, in case somebody changed one by hand
    if PLAN.rescan > 0 and os.clock() - lastScan >= PLAN.rescan then
      rescan()
      lastScan = os.clock()
    end
    toCell(0)
    turnTo(1)
    local t, stacks = totals()
    local kinds = 0
    for _ in pairs(t) do kinds = kinds + 1 end
    status("Waiting for deliveries", kinds .. " kinds, " .. stacks .. " stacks, " .. built .. "/" .. MAXC .. " chests",
           chestsHeld() > 0 and "" or (built >= MAXC and "Warehouse is at its maximum." or "Out of spare chests. Add some."))
    sleep(PLAN.wait)
  end
end

if rawget(_G, "CARVE_TEST") then
  return { main = main, pos = pos }
end
runMain(main)
