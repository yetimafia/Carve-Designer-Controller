-- Carve scout: walks (and flies) through open space, looks at every block around it and reports what it
-- sees to the Designer's Fleet map. It never digs, never places and never enters water or lava.
-- Stand on the START cell facing forward (+z). It explores within PLAN.radius blocks of the start and from
-- PLAN.down below to PLAN.up above it, then comes back. Fuel: put coal (or anything burnable) in its inventory.
-- Run again with  stop  to cancel the automatic restart.

local args = { ... }

--@@PLAN@@

local STATE_FILE = "carve.scout"
local TITLE = PLAN.name or "Scout"
local FUEL_HINT = "coal, charcoal or wood"
local BURN = { "coal", "charcoal", "log", "planks", "stick" }

--@@COMMON@@

local R, UP, DOWN = PLAN.radius, PLAN.up, PLAN.down
local home = { 0, 0, 0 }
local known = {}                -- key -> block name ("air" for empty space)
local seen = 0                  -- how many cells are known
local visited = {}
local nvisited = 0
local outbox = {}               -- cells not yet sent to the app
local lastFlush = 0

local function key(x, y, z) return ((x + 256) * 512 + (z + 256)) * 512 + (y + 256) end
local function inside(x, y, z) return math.abs(x) <= R and math.abs(z) <= R and y >= -DOWN and y <= UP end

local function learn(x, y, z, name)
  local k = key(x, y, z)
  if known[k] then return end
  known[k] = name
  seen = seen + 1
  outbox[#outbox + 1] = { x, y, z, name }
end

local function flush(force)
  if #outbox == 0 or not fleet.on then outbox = fleet.on and outbox or {}; return end
  if not force and #outbox < 60 and os.clock() - lastFlush < 5 then return end
  lastFlush = os.clock()
  while #outbox > 0 do
    local parts, sent = {}, {}
    for i = 1, math.min(#outbox, 400) do
      local c = table.remove(outbox)
      sent[#sent + 1] = c
      parts[#parts + 1] = "[" .. c[1] .. "," .. c[2] .. "," .. c[3] .. "," .. jq(c[4]) .. "]"
    end
    local ok, res = pcall(http.post, { url = LIVE_URL .. "/map", timeout = 5, headers = { ["Content-Type"] = "application/json" },
      body = '{"v":1,"id":' .. os.getComputerID() .. ',"cells":[' .. table.concat(parts, ",") .. "]}" })
    if ok and res then
      pcall(function() res.readAll(); res.close() end)
    else
      for _, part in ipairs(sent) do outbox[#outbox + 1] = part end      -- the app didn't get them: keep them and try again later
      break
    end
  end
end

-- what is in front of / above / below me
local function look(d)
  local ok, data
  if d == 5 then ok, data = turtle.inspectUp()
  elseif d == 6 then ok, data = turtle.inspectDown()
  else ok, data = turtle.inspect() end
  if not ok then return "air" end
  return type(data) == "table" and data.name or "unknown"
end

local function nx(d) return pos.x + DX[d], pos.y + DY[d], pos.z + DZ[d] end

-- look at all six neighbours (turning only when a side is still unknown)
local function scan()
  for _, d in ipairs({ 5, 6 }) do
    local x, y, z = nx(d)
    if not known[key(x, y, z)] then learn(x, y, z, look(d)) end
  end
  for step = 0, 3 do
    local d = (face - 1 + step) % 4 + 1
    local x, y, z = nx(d)
    if not known[key(x, y, z)] then
      turnTo(d)
      learn(x, y, z, look(d))
    end
  end
end

-- one move to a neighbouring cell that is known to be empty; false if something is in the way
local function move(d)
  ensureFuel()
  if d <= 4 then turnTo(d) end
  local fn = d == 5 and turtle.up or d == 6 and turtle.down or turtle.forward
  for _ = 1, 3 do
    if fn() then
      pos.x, pos.y, pos.z = pos.x + DX[d], pos.y + DY[d], pos.z + DZ[d]
      savePos()
      return true
    end
    sleep(0.5)
  end
  local x, y, z = nx(d)
  known[key(x, y, z)] = "blocked"          -- something we can't see (a mob, a block that changed): don't try again
  return false
end

-- shortest way through known empty cells from here to the nearest cell that satisfies goal(x, y, z)
local function route(goal)
  local start = key(pos.x, pos.y, pos.z)
  local prev, queue, head = { [start] = false }, { { pos.x, pos.y, pos.z } }, 1
  while head <= #queue do
    local c = queue[head]
    head = head + 1
    if goal(c[1], c[2], c[3]) then
      local path, k = {}, key(c[1], c[2], c[3])
      while prev[k] do
        table.insert(path, 1, prev[k][2])
        k = prev[k][1]
      end
      return path
    end
    for d = 1, 6 do
      local x, y, z = c[1] + DX[d], c[2] + DY[d], c[3] + DZ[d]
      local k = key(x, y, z)
      if prev[k] == nil and known[k] == "air" and inside(x, y, z) then
        prev[k] = { key(c[1], c[2], c[3]), d }
        queue[#queue + 1] = { x, y, z }
      end
    end
    if head % 400 == 0 then sleep(0) end
  end
  return nil
end

local function isFrontier(x, y, z)
  return not visited[key(x, y, z)]
end

-- go back to the start cell by the known way (waits for fuel if needed)
local function goHome()
  local path = route(function(x, y, z) return x == home[1] and y == home[2] and z == home[3] end)
  if not path then return false end
  for _, d in ipairs(path) do
    if not move(d) then return false end
  end
  return true
end

local function visit()
  local k = key(pos.x, pos.y, pos.z)
  if not visited[k] then visited[k] = true; nvisited = nvisited + 1 end
  known[k] = "air"
  scan()
  if nvisited % 4 == 0 then
    fleet.n, fleet.total = seen, 0
    say(TITLE, "", "Scouting: " .. nvisited .. " places visited", seen .. " blocks seen", "At " .. pos.x .. " " .. pos.y .. " " .. pos.z)
  end
  flush(false)
end

local function fuelNow()
  local f = turtle.getFuelLevel()
  return f == "unlimited" and math.huge or f
end

-- false when fuel is too low to keep going and still get home
local function explore()
  visit()
  while true do
    local path = route(isFrontier)
    if not path then return true end                      -- nothing reachable is left to look at
    local need = (math.abs(pos.x - home[1]) + math.abs(pos.y - home[2]) + math.abs(pos.z - home[3])) * 2 + #path + 30
    if fuelNow() < need then
      burn(need + 200)
      if fuelNow() < need then return false end
    end
    for _, d in ipairs(path) do
      if not move(d) then break end
    end
    visit()
  end
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
    home = { pos.x, pos.y, pos.z }                        -- what it knew is gone: finish where it stands
  else
    fs.delete(STATE_FILE)
    pos.x, pos.y, pos.z, face = 0, 0, 0, 1
    savePos()
  end
  installStartup()
  while true do
    local complete = explore()
    flush(true)
    if complete then break end
    goHome()
    while fuelNow() < 400 do
      say(TITLE, "", "Low on fuel - waiting at the start.", "Put " .. FUEL_HINT .. " in my inventory.")
      sleep(10)
      burn(1000)
    end
  end
  goHome()
  turnTo(1)
  flush(true)
  removeStartup()
  fs.delete(STATE_FILE)
  finish(TITLE, "", "Done. " .. seen .. " blocks mapped", "from " .. nvisited .. " places.")
end

if rawget(_G, "CARVE_TEST") then
  return { main = main, pos = pos }
end
runMain(main)
