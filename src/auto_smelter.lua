-- Carve auto smelter: feeds a row of furnaces from an input chest and puts the results in an output chest.
--
-- Layout (top view, you stand on START facing the furnaces, "F" = furnace, it needs free air above and below):
--        F F F F ...        furnaces, 2 blocks in front of the start row
--        . . . . ...        the turtle's walkway (1 block in front)
--      [out] T              T = START, [out] = output chest on its left, [in] = input chest behind it
--            [in]
-- Put raw items AND your fuel (coal) in the input chest. Run with  setup  to let the turtle place the furnaces.
-- It can't dig out furnaces or chests, but it will dig dirt/stone out of its own way (it walks above and below the furnaces).
--
-- VERSION NOTES
--   - 8.2: every pile is split evenly over all furnaces so they run at the same time (allocate); charcoal is the preferred fuel and a
--     reserve of two rounds is kept (KEEP_CHARCOAL), the surplus goes to the output chest and on into storage.

local args = { ... }

--@@PLAN@@

local STATE_FILE = "carve.smelter"
local TITLE = PLAN.name or "Auto smelter"
local FUEL = PLAN.fuel or "minecraft:coal"
local FUEL_HINT = FUEL:gsub("^minecraft:", "")
local BURN = { (FUEL:gsub("^minecraft:", "")), "charcoal" }
local KEEP = {}

--@@COMMON@@

local F = PLAN.furnaces

-- how many items one piece of fuel smelts
local FUEL_ITEMS = { coal = 8, charcoal = 8, coal_block = 80, lava_bucket = 100, blaze_rod = 12,
                     log = 1.5, planks = 1.5, wood = 1.5, stick = 0.5 }
local PER_FUEL = 1.5
do
  local short = FUEL:gsub("^minecraft:", "")
  for k, v in pairs(FUEL_ITEMS) do
    if short:find(k, 1, true) then PER_FUEL = v end
  end
end
local KEEP_FUEL = 64                                   -- how much of my own coal I hold on to
local KEEP_CHARCOAL = math.max(64, F * 16)              -- charcoal kept to run every furnace for two rounds; the rest goes to the output chest (and so into storage)

local CHARCOAL = "minecraft:charcoal"
local SWITCH_AT = 32          -- once I hold this much charcoal I burn that instead of coal or wood
local function isWood(n) return n ~= nil and (n:find("log", 1, true) or n:find("planks", 1, true) or n:find("_wood", 1, true)) ~= nil end
local function isFuelName(n) return n == FUEL or n == CHARCOAL or n == "minecraft:coal" end

local function slotsOf(name)
  local t = {}
  for s = 1, 16 do
    if itemName(s) == name then t[#t + 1] = s end
  end
  return t
end

local function countOf(name)
  local n = 0
  for _, s in ipairs(slotsOf(name)) do n = n + turtle.getItemCount(s) end
  return n
end

local function fuelSlots()
  return slotsOf(FUEL)
end

local function fuelCount()
  return countOf(FUEL)
end

local function perFuel(name)
  local short = (name or ""):gsub("^minecraft:", "")
  local v = 1.5
  for k, x in pairs(FUEL_ITEMS) do
    if short:find(k, 1, true) then v = x end
  end
  return v
end

-- what to burn for `name`: charcoal as soon as I have some (it is made from the logs, so it never runs out), else my coal, else the wood itself
local function chooseFuel(name)
  if name ~= CHARCOAL and countOf(CHARCOAL) > 1 then return CHARCOAL end
  if countOf(FUEL) > 1 then return FUEL end
  if countOf("minecraft:coal") > 1 then return "minecraft:coal" end
  if isWood(name) then return name end                       -- bootstrap: burn some of the logs to make the first charcoal
  for s = 1, 16 do
    if isWood(itemName(s)) then return itemName(s) end
  end
  return nil
end

local function home()
  goTo(pos.x, 0, 1, "y")
  goTo(0, 0, 1, "x")
  goTo(0, 0, 0, "z")
end

-- walk to the walkway cell in front of furnace k (k = 1 .. F) facing the furnace
local function toFurnace(k)
  goTo(k - 1, 0, 1, "yzx")
  turnTo(1)
end

-- take what is in the input chest into my inventory (keeps two slots free)
local function pull()
  turnTo(3)
  local got = false
  for _ = 1, 60 do
    if freeSlots() < 3 then break end
    if not turtle.suck() then break end
    got = true
  end
  return got
end

-- put the smelted items (and anything else that is not on its way to a furnace) in the output chest
local function unload(pending)
  local keep = {}
  for s in pairs(pending or {}) do keep[s] = true end
  for _, spec in ipairs({ { FUEL, KEEP_FUEL }, { CHARCOAL, KEEP_CHARCOAL } }) do      -- fuel I need stays; anything above goes on
    local held = 0
    for _, s in ipairs(slotsOf(spec[1])) do
      if held < spec[2] then keep[s] = true; held = held + turtle.getItemCount(s) end
    end
  end
  turnTo(4)
  dumpFront(keep)
  turnTo(1)
end

-- drop n of item `name` with `fn` (turtle.drop = into the furnace's fuel slot, turtle.dropDown = its input slot); returns how many went in
local function dropN(name, n, fn)
  local gone = 0
  for _, s in ipairs(slotsOf(name)) do
    if gone >= n then break end
    turtle.select(s)
    local before = turtle.getItemCount(s)
    fn(math.min(n - gone, before))
    gone = gone + (before - turtle.getItemCount(s))
  end
  turtle.select(1)
  return gone
end

local fuelNote = ""
-- one furnace gets e.count items of e.name plus the fuel for them
local function feed(k, e)
  toFurnace(k)
  local fuel = chooseFuel(e.name)
  local input = e.count
  if fuel == e.name then                                    -- burning the very logs I am smelting: some of them become the fuel
    local f = math.ceil(e.count * 0.4)
    input = e.count - f
    dropN(e.name, f, turtle.drop)
    fuelNote = "burning logs for fuel"
  elseif fuel then
    local keepOne = (fuel == FUEL or fuel == "minecraft:coal") and 1 or 0     -- one coal for the turtle itself
    dropN(fuel, math.min(math.ceil(e.count / perFuel(fuel)), countOf(fuel) - keepOne), turtle.drop)
    fuelNote = "burning " .. fuel:gsub("^minecraft:", "")
  else
    fuelNote = "no fuel: waiting for logs or coal"
  end
  step(5); step(1)                                          -- above the furnace
  dropN(e.name, input, turtle.dropDown)
  step(3); step(6)
end

-- what I hold to smelt, as totals per kind (biggest pile first)
local function piles()
  local total, order = {}, {}
  for s = 1, 16 do
    local n = itemName(s)
    if n and not isFuelName(n) and not isBuildItem(n) then
      if not total[n] then total[n] = 0; order[#order + 1] = n end
      total[n] = total[n] + turtle.getItemCount(s)
    end
  end
  table.sort(order, function(a, b) return total[a] > total[b] end)
  return total, order
end

-- who gets what: every kind gets a furnace, the spare furnaces go to the biggest piles, and each pile is split evenly over its
-- furnaces so all of them work at the same time (a furnace takes at most one stack)
-- v8.2: before, one stack went into one furnace, so a single big pile of cobblestone used one furnace. Now each kind gets its own furnaces and the
-- spare furnaces share the biggest piles.
local function allocate(total, order)
  local assigned, used = {}, 0
  for _, n in ipairs(order) do
    if used < F then assigned[n] = 1; used = used + 1 end
  end
  while used < F do
    local best, load = nil, 1
    for _, n in ipairs(order) do
      local a = assigned[n]
      if a and a < total[n] and total[n] / a > load then best, load = n, total[n] / a end
    end
    if not best then break end
    assigned[best] = assigned[best] + 1; used = used + 1
  end
  local list = {}
  for _, n in ipairs(order) do
    local a = assigned[n]
    if a then
      local sum = math.min(total[n], a * 64)
      for i = 1, a do list[#list + 1] = { name = n, count = math.floor(sum / a) + (i <= sum % a and 1 or 0) } end
    end
  end
  return list
end

local function collect(k)
  toFurnace(k)
  step(6); step(1)                                  -- below the furnace
  local n = 0
  while turtle.suckUp() do
    n = n + 1
    if n > 10 or freeSlots() < 1 then break end
  end
  step(3); step(5)
end

local function furnaceSlot()
  for s = 1, 16 do
    if itemName(s) == "minecraft:furnace" then return s end
  end
end

-- place the missing furnaces (and the two chests). With waitForItems it waits until somebody hands me the furnaces.
local function setup(waitForItems)
  ensureChest(3, "raw items")
  ensureChest(4, "results")
  turnTo(1)
  for k = 1, F do
    toFurnace(k)
    local ok, data = turtle.inspect()
    if not (ok and has(data.name, "furnace")) then
      if ok then turtle.dig() end
      local s = furnaceSlot()
      while not s do
        if not waitForItems then
          say(TITLE, "", "Put " .. F .. " furnaces in my inventory", "(furnace " .. k .. " is missing), then", "run setup again.")
          home(); turnTo(1)
          return false
        end
        say(TITLE, "", "Put furnaces in my inventory", "(furnace " .. k .. "/" .. F .. " is missing). Waiting...")
        sleep(5)
        s = furnaceSlot()
      end
      turtle.select(s)
      turtle.place()
    end
  end
  turtle.select(1)
  home(); turnTo(1)
  return true
end

local function recover()
  if pos.y ~= 0 then goTo(pos.x, 0, pos.z, "y") end
  home()
end

local function main()
  if not turtle then printError("This program must run on a turtle."); return end
  if args[1] == "stop" then
    removeStartup(); fs.delete(STATE_FILE)
    finish(TITLE, "", "Stopped. The automatic restart is removed.")
    return
  end
  if args[1] == "resume" and loadPos() then
    say(TITLE, "", "Resuming after a restart...")
    recover()
  else
    fs.delete(STATE_FILE)
    pos.x, pos.y, pos.z, face = 0, 0, 0, 1
    savePos()
  end
  if args[1] == "setup" then
    if setup(false) then
      say(TITLE, "", "Furnaces and chests are in place.", "Chest BEHIND me = input,", "chest on my LEFT = output.", "Run me again without setup.")
    end
    return
  end
  installStartup()
  setup(true)                                        -- builds whatever is missing: chests from my inventory, furnaces
  local idle, stuck = 0, 0
  while true do
    pull()
    local total, order = piles()
    if #order == 0 then
      turnTo(1)
      idle = idle + 1
      if PLAN.once then break end
      waitSeconds(30, "Nothing to smelt. Waiting for items.")
    else
      idle = 0
      local list = allocate(total, order)
      local before, longest = 0, 0
      for _, e in ipairs(list) do longest = math.max(longest, e.count) end
      for _, n in ipairs(order) do before = before + total[n] end
      for i, e in ipairs(list) do
        say(TITLE, "", "Loading furnace " .. i .. "/" .. #list, "Items " .. e.count .. " x " .. e.name:gsub("^minecraft:", ""),
            fuelNote ~= "" and fuelNote or ("charcoal " .. countOf(CHARCOAL) .. "/" .. KEEP_CHARCOAL))
        feed(i, e)
      end
      home()
      waitSeconds(longest * 10 + 6, "Smelting in " .. #list .. " furnace(s)...")
      for i = 1, #list do collect(i) end
      home()
      -- what is left of the kinds I loaded stays in me for the next round; the products and the rest go to the output chest
      local pending, left = {}, 0
      for s = 1, 16 do
        local n = itemName(s)
        if n and total[n] then pending[s] = true; left = left + turtle.getItemCount(s) end
      end
      stuck = left < before and 0 or stuck + 1
      if stuck >= 2 then
        say(TITLE, "", "Some items won't go into the", "furnaces (not smeltable?).", "Putting them in the output chest.")
        pending = {}
        stuck = 0
      end
      unload(pending)
    end
  end
  removeStartup()
  fs.delete(STATE_FILE)
  finish(TITLE, "", "All done. Output is in the chest.")
end

if rawget(_G, "CARVE_TEST") then
  return { main = main, pos = pos }
end
runMain(main)
