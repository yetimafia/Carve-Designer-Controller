-- Carve auto crafter: crafts one recipe over and over from an input chest into an output chest.
-- It must be a CRAFTY turtle (a turtle with a crafting table). Chest BEHIND the start = ingredients,
-- chest on the LEFT = results. The recipe is stored in this program (3x3 grid, row by row).

local args = { ... }

--@@PLAN@@

local STATE_FILE = "carve.crafter"
local TITLE = PLAN.name or "Auto crafter"
local FUEL_HINT = "coal"
local BURN = { "coal", "charcoal" }
local KEEP = {}

--@@COMMON@@

local GRID = { 1, 2, 3, 5, 6, 7, 9, 10, 11 }
local RESULT = 16

local function need()
  local c, order = {}, {}
  for i = 1, 9 do
    local n = PLAN.grid[i]
    if n then
      if not c[n] then c[n] = 0; order[#order + 1] = n end
      c[n] = c[n] + 1
    end
  end
  return c, order
end
local CELLS, INGREDIENTS = need()

local function totals()
  local t = {}
  for s = 1, 16 do
    local n = itemName(s)
    if n and CELLS[n] then t[n] = (t[n] or 0) + turtle.getItemCount(s) end
  end
  return t
end

local function pull()
  turnTo(3)
  for _ = 1, 60 do
    if freeSlots() < 2 then break end
    if not turtle.suck() then break end
  end
end

-- everything that is not an ingredient is a result: output chest; ingredients that are left go back
local function putAway()
  turnTo(4)
  for s = 1, 16 do
    local n = itemName(s)
    if n and not CELLS[n] then turtle.select(s); turtle.drop() end
  end
  turnTo(3)
  for s = 1, 16 do
    local n = itemName(s)
    if n and CELLS[n] then turtle.select(s); turtle.drop() end
  end
  turtle.select(1)
  turnTo(1)
end

local function isGrid(s)
  for _, g in ipairs(GRID) do if g == s then return true end end
  return false
end

local function emptySlotNot(avoid)
  for s = 16, 1, -1 do
    if turtle.getItemCount(s) == 0 and not avoid[s] then return s end
  end
  return nil
end

-- lay out `b` of every ingredient in the right grid cells. false if it can't be done
local function arrange(b)
  local filled = {}
  local targets = {}
  for i = 1, 9 do if PLAN.grid[i] then targets[GRID[i]] = true end end
  -- clear the result slot and any grid slot that holds the wrong thing
  for i = 1, 9 do
    local s = GRID[i]
    local want = PLAN.grid[i]
    local have = itemName(s)
    if have and have ~= want then
      local free = emptySlotNot(targets)
      if not free then return false end
      turtle.select(s); turtle.transferTo(free)
    end
  end
  if turtle.getItemCount(RESULT) > 0 then
    local free = emptySlotNot(targets)
    if not free then return false end
    turtle.select(RESULT); turtle.transferTo(free)
  end
  for i = 1, 9 do
    local want = PLAN.grid[i]
    if want then
      local s = GRID[i]
      local guard = 0
      while turtle.getItemCount(s) < b and guard < 40 do
        guard = guard + 1
        local donor
        for d = 1, 16 do
          if d ~= s and not filled[d] and itemName(d) == want and turtle.getItemCount(d) > 0 then donor = d; break end
        end
        if not donor then return false end
        turtle.select(donor)
        turtle.transferTo(s, b - turtle.getItemCount(s))
      end
      if turtle.getItemCount(s) > b then
        -- more than needed here: give the extra back to another slot
        local free = emptySlotNot(targets)
        if free then turtle.select(s); turtle.transferTo(free, turtle.getItemCount(s) - b) end
      end
      filled[s] = true
    end
  end
  turtle.select(1)
  return true
end

local function main()
  if not turtle then printError("This program must run on a turtle."); return end
  if not turtle.craft then
    say(TITLE, "", "This turtle can't craft.", "Craft a crafty turtle (turtle", "+ crafting table) and use that.")
    return
  end
  if args[1] == "stop" then
    removeStartup(); fs.delete(STATE_FILE)
    finish(TITLE, "", "Stopped. The automatic restart is removed.")
    return
  end
  face = 1
  installStartup()
  ensureChest(3, "ingredients")
  ensureChest(4, "results")
  turnTo(1)
  local made = 0
  local wait = 0
  while true do
    pull()
    local have = totals()
    local b = 64
    for n, c in pairs(CELLS) do b = math.min(b, math.floor((have[n] or 0) / c)) end
    if PLAN.total > 0 then b = math.min(b, PLAN.total - made) end
    if b <= 0 then
      putAway()
      if PLAN.total > 0 and made >= PLAN.total then break end
      if PLAN.once then break end
      waitSeconds(20, "Waiting for ingredients. Crafted " .. made .. " so far.")
    else
      say(TITLE, "", "Crafting " .. b .. " ...", "Done so far: " .. made)
      -- return the items that are not ingredients before we shuffle slots
      turnTo(4)
      for s = 1, 16 do
        local n = itemName(s)
        if n and not CELLS[n] then turtle.select(s); turtle.drop() end
      end
      turnTo(1)
      if not arrange(b) then
        putAway()
        say(TITLE, "", "Could not lay the recipe out.", "Is my inventory too full?")
        break
      end
      turtle.select(RESULT)
      local ok = turtle.craft(b)
      turtle.select(1)
      if not ok then
        putAway()
        say(TITLE, "", "That recipe did not craft.", "Check the grid in the designer.")
        break
      end
      made = made + b
      fleet.n, fleet.total = made, PLAN.total
      putAway()
    end
  end
  removeStartup()
  fs.delete(STATE_FILE)
  finish(TITLE, "", "Finished. Crafted " .. made .. " time(s).")
end

if rawget(_G, "CARVE_TEST") then
  return { main = main }
end
runMain(main)
