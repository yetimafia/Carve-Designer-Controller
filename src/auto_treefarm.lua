-- Carve tree farm: plants saplings on a grid, waits (or uses bone meal), chops the trees,
-- replants and keeps the logs in the chest behind the start. Stop it with Ctrl+T; it resumes by itself.
-- Setup: flat ground (dirt or grass) with free space. Stand on the START cell facing the first row.
--   slot 1 = saplings, slot 2 = bone meal (only if you chose to use it). A chest goes right behind the start.
-- Run again with  stop  to cancel the automatic restart.

local args = { ... }

--@@PLAN@@

local STATE_FILE = "carve.farm"
local TITLE = PLAN.name or "Tree farm"
local FUEL_HINT = "logs, sticks or coal"
local BURN = { "log", "stick", "coal", "charcoal", "planks" }
local KEEP = {}

--@@COMMON@@

local SAPLING_SLOT, BONE_SLOT = 1, 2
local cycle = 0

local SAP = PLAN.sapling                -- the kind I plant; changes if I was given another kind of sapling

local function isAnySapling(name)
  return name ~= nil and (name:find("sapling", 1, true) ~= nil or name:find("propagule", 1, true) ~= nil)
end

local function isSapling(name)
  if not name then return false end
  if SAP == "any" then return isAnySapling(name) end
  return name == SAP
end

-- look through the whole inventory: if there are none of the chosen kind but there are saplings of another kind, plant those
local function adoptSaplings()
  local count, best = {}, nil
  for s = 1, 16 do
    local n = itemName(s)
    if isAnySapling(n) then
      count[n] = (count[n] or 0) + turtle.getItemCount(s)
      if not best or count[n] > count[best] then best = n end
    end
  end
  if SAP ~= "any" and (count[SAP] or 0) == 0 and best then
    SAP = best
    say(TITLE, "", "No " .. tostring(PLAN.sapling):gsub("minecraft:", "") .. " found.", "Planting " .. best:gsub("minecraft:", "") .. " instead.")
    sleep(2)
  end
end

-- move whatever is in slot `s` to another empty slot (false if there is none)
local function clearSlot(s)
  for t = 16, 1, -1 do
    if t ~= s and turtle.getItemCount(t) == 0 then
      turtle.select(s)
      turtle.transferTo(t)
      turtle.select(1)
      return true
    end
  end
  return false
end

-- make slot 1 hold saplings of the right kind (collect them from other slots)
local function gatherSaplings()
  local first = itemName(SAPLING_SLOT)
  if first and not isSapling(first) then clearSlot(SAPLING_SLOT) end
  for s = 1, 16 do
    if s ~= SAPLING_SLOT and isSapling(itemName(s)) then
      local here = itemName(SAPLING_SLOT)
      if here == nil or here == itemName(s) then
        turtle.select(s)
        turtle.transferTo(SAPLING_SLOT)
      end
    end
  end
  if PLAN.bonemeal then                                       -- and bone meal in slot 2, wherever I was handed it
    local second = itemName(BONE_SLOT)
    if second and not has(second, "bone_meal") then clearSlot(BONE_SLOT) end
    for s = 1, 16 do
      if s ~= SAPLING_SLOT and s ~= BONE_SLOT and has(itemName(s), "bone_meal") then
        local here = itemName(BONE_SLOT)
        if here == nil or has(here, "bone_meal") then
          turtle.select(s)
          turtle.transferTo(BONE_SLOT)
        end
      end
    end
  end
  turtle.select(1)
end

local function saplingsLeft()                       -- every slot counts, not just slot 1
  local n = 0
  for s = 1, 16 do
    if isSapling(itemName(s)) then n = n + turtle.getItemCount(s) end
  end
  return n
end

local function boneLeft()
  if not PLAN.bonemeal then return 0 end
  local n = itemName(BONE_SLOT)
  return (n and n:find("bone_meal", 1, true)) and turtle.getItemCount(BONE_SLOT) or 0
end

local function front()
  local ok, data = turtle.inspect()
  if not ok then return nil end
  return data.name or "?"
end

local function chop()
  turtle.dig()
  step(1)                                 -- into the trunk's base cell
  while true do
    local ok, data = turtle.inspectUp()
    if ok and (has(data.name, "log") or has(data.name, "wood") or has(data.name, "stem")) then
      turtle.digUp()
      step(5)
    else
      break
    end
  end
  while pos.y > 0 do step(6) end
  for _ = 1, 3 do turtle.suckDown() ; turtle.suck(); turtle.suckUp() end   -- saplings and apples that fell here
  step(3)                                 -- back to where I stood
  turnTo(1)
  for _ = 1, 3 do turtle.suck() end
  gatherSaplings()
end

local function plant()
  if not isSapling(itemName(SAPLING_SLOT)) then gatherSaplings() end       -- slot 1 ran out: refill it from the other slots
  if saplingsLeft() == 0 then return false end
  turtle.select(SAPLING_SLOT)
  local ok = turtle.place()
  turtle.select(1)
  return ok
end

local function useBone()
  local tries = 0
  while boneLeft() > 0 and tries < 8 do
    local n = front()
    if not has(n, "sapling") and not has(n, "propagule") then break end
    turtle.select(BONE_SLOT)
    turtle.place()
    turtle.select(1)
    tries = tries + 1
  end
end

-- what to do at one spot (I stand next to it, looking at it). Returns "chopped", "planted", "growing" or "skipped"
local function handleSpot()
  turnTo(1)
  local n = front()
  local result
  if n == nil then
    result = plant() and "planted" or "skipped"
  elseif has(n, "log") or has(n, "wood") or has(n, "stem") then
    chop()
    plant()
    result = "chopped"
  elseif has(n, "leaves") then
    turtle.dig()
    result = plant() and "planted" or "skipped"
  elseif has(n, "sapling") or has(n, "propagule") then
    result = "growing"
  else
    result = "skipped"
  end
  if PLAN.bonemeal and (result == "planted" or result == "growing" or result == "chopped") then
    useBone()
    n = front()
    if n and (has(n, "log") or has(n, "wood") or has(n, "stem")) then
      chop()
      plant()
      useBone()
      result = "chopped"
    elseif n and (has(n, "sapling") or has(n, "propagule")) then
      result = "growing"
    end
  end
  return result
end

local function home()
  goTo(0, 0, pos.z, "y")
  goTo(0, 0, pos.z, "x")
  goTo(0, 0, 0, "z")
  turnTo(1)
end

local function unload()
  home()
  gatherSaplings()
  burn(500)
  local keep = {}
  for s = 1, 16 do
    if isSapling(itemName(s)) then keep[s] = true end                       -- never drop saplings into the chest
  end
  if PLAN.bonemeal and has(itemName(BONE_SLOT), "bone_meal") then keep[BONE_SLOT] = true end
  if PLAN.chest then
    turnTo(3)
    dumpFront(keep)
    turnTo(1)
  elseif freeSlots() < 3 then
    while freeSlots() < 3 do
      say(TITLE, "", "Inventory full - empty me.", "Waiting...")
      sleep(3)
    end
  end
end

-- walk to the lane of row z (only ever along the free corridor at x = 0 and the lane cells)
local function toLane(z)
  goTo(0, 0, pos.z, "yx")
  goTo(0, 0, z, "z")
end

local function pass()
  local stats = { chopped = 0, planted = 0, growing = 0, skipped = 0 }
  local S = PLAN.spacing
  for j = 0, PLAN.rows - 1 do
    local z = j * S
    toLane(z)                             -- via the free corridor at x = 0
    for i = 1, PLAN.cols do
      local x = i * S
      goTo(x, 0, z, "x")
      say(TITLE, "", "Row " .. (j + 1) .. "/" .. PLAN.rows .. "  tree " .. i .. "/" .. PLAN.cols,
          "Cycle " .. (cycle + 1), "Saplings " .. saplingsLeft() .. "  bone meal " .. boneLeft())
      local r = handleSpot()
      stats[r] = stats[r] + 1
      if freeSlots() < 2 then
        if PLAN.chest then unload(); toLane(z); goTo(x, 0, z, "x") end
      end
    end
    goTo(0, 0, z, "x")
  end
  return stats
end

-- after a restart the turtle may be up a tree or standing where a tree is: get back to the corridor
local function recover()
  while pos.y > 0 do step(6) end
  while pos.y < 0 do step(5) end
  if pos.z % PLAN.spacing ~= 0 then
    goTo(pos.x, 0, pos.z - (pos.z % PLAN.spacing), "z")
  end
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
  installStartup()
  if PLAN.chest then ensureChest(3, "logs"); turnTo(1) end      -- place my own chest behind the start if there is none
  adoptSaplings()
  gatherSaplings()
  if args[1] ~= "resume" then
    while saplingsLeft() == 0 do
      say(TITLE, "", "No saplings in my inventory.", "Put some in (any slot). Waiting...")
      sleep(5)
      adoptSaplings()
    end
    gatherSaplings()
  end
  while true do
    local st = pass()
    cycle = cycle + 1
    fleet.n, fleet.total = cycle, PLAN.cycles
    unload()
    if PLAN.cycles > 0 and cycle >= PLAN.cycles then break end
    if not (PLAN.bonemeal and st.growing == 0 and boneLeft() > 0) then
      waitSeconds(PLAN.wait, "Chopped " .. st.chopped .. " planted " .. st.planted .. " growing " .. st.growing)
    end
  end
  removeStartup()
  fs.delete(STATE_FILE)
  finish(TITLE, "", "Done after " .. cycle .. " cycle(s).")
end

if rawget(_G, "CARVE_TEST") then
  return { main = main, pos = pos }
end
runMain(main)
