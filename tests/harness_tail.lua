---------------------------------------------------------------- test scaffolding
local function id(c, x, y, z) return ((y - 1) * c.d + (z - 1)) * c.w + x end
local initial

local function resetTurtle(c)
  T = { x = 0, y = 0, z = 0, f = 0 }
  fuel, inv, selSlot = c.fuel or 2000, {}, 1
  fuelUnlimited = c.unlimited or false
  noTool = c.noTool or false
  burned, initialItems = 0, c.coal or 0
  if (c.coal or 0) > 0 then inv[16] = { name = "minecraft:coal", count = c.coal } end
  chestStore, lost, droppedGround, digCount, actions = {}, 0, 0, 0, 0
  abortAfter, visited, chestDug = nil, {}, false
  sleepCount = 0
  files = {}
  events = {}
  OUT_START = #OUT
end

local function buildWorld(c)
  W = {}
  local special = {}
  for _, s in ipairs(c.special or {}) do special[id(c, s[1], s[2], s[3])] = s[4] end
  for y = 1, c.h do for z = 1, c.d do for x = 1, c.w do
    W[key(x - c.tx, y - c.ty, z - c.tz)] = special[id(c, x, y, z)] or "stone"
  end end end
  W[key(0, 0, 0)] = nil
  if c.worldChest then W[key(0, 0, -1)] = "chest" end
  initial = {}
  for k, v in pairs(W) do initial[k] = v end
end

-- the selection exactly as the designer describes it, independent of the engine
local function parseSel(c)
  local sel = {}
  for y = 1, c.h do
    local row = c.layers[y]
    for i = 1, #row do
      if row:byte(i) == 49 then sel[(y - 1) * c.d * c.w + i] = true end
    end
  end
  return sel
end

local function expectedReach(c)
  local sel = parseSel(c)
  local start = id(c, c.tx, c.ty, c.tz)
  sel[start] = true
  if c.chest and c.tz > 1 then sel[id(c, c.tx, c.ty, c.tz - 1)] = nil end
  local reach, q, head = { [start] = true }, { { c.tx, c.ty, c.tz } }, 1
  local D = { { 1, 0, 0 }, { -1, 0, 0 }, { 0, 1, 0 }, { 0, -1, 0 }, { 0, 0, 1 }, { 0, 0, -1 } }
  while head <= #q do
    local x, y, z = q[head][1], q[head][2], q[head][3]
    head = head + 1
    for _, dd in ipairs(D) do
      local nx, ny, nz = x + dd[1], y + dd[2], z + dd[3]
      if nx >= 1 and nx <= c.w and ny >= 1 and ny <= c.h and nz >= 1 and nz <= c.d then
        local i = id(c, nx, ny, nz)
        if not reach[i] and sel[i] and initial[key(nx - c.tx, ny - c.ty, nz - c.tz)] ~= "bedrock" then
          reach[i] = true
          q[#q + 1] = { nx, ny, nz }
        end
      end
    end
  end
  return reach
end

local function itemCheck(errs)
  local held, stored = 0, 0
  for i = 1, 16 do held = held + (inv[i] and inv[i].count or 0) end
  for _, n in pairs(chestStore) do stored = stored + n end
  if held + stored + droppedGround + lost + burned ~= digCount + initialItems then
    errs[#errs + 1] = ("item leak: held %d stored %d ground %d lost %d burned %d dug %d start %d"):format(
      held, stored, droppedGround, lost, burned, digCount, initialItems)
  end
  if lost > 0 then errs[#errs + 1] = "items lost (inventory overflow): " .. lost end
  if droppedGround > 0 then errs[#errs + 1] = "items dropped on the ground: " .. droppedGround end
  if chestDug then errs[#errs + 1] = "CHEST WAS DUG" end
  return stored
end

local function finishLine(c, errs, extra)
  log(("%-38s %s %s"):format(c.name, #errs == 0 and "PASS" or "FAIL", extra or ""))
  for i = 1, math.min(#errs, 6) do log("    " .. errs[i]) end
  return #errs == 0
end

-- the job ran to completion: every reachable block gone, nothing else touched, turtle home
local function verifyDone(c)
  local errs = {}
  local reach = expectedReach(c)
  local expected = 0
  for y = 1, c.h do for z = 1, c.d do for x = 1, c.w do
    local k = key(x - c.tx, y - c.ty, z - c.tz)
    if reach[id(c, x, y, z)] and initial[k] == "stone" then
      expected = expected + 1
      if W[k] ~= nil then errs[#errs + 1] = "NOT MINED " .. k end
    elseif W[k] ~= initial[k] then
      errs[#errs + 1] = "CHANGED " .. k .. " " .. tostring(initial[k]) .. "->" .. tostring(W[k])
    end
  end end end
  if c.py_total and not c.special and c.py_total ~= expected then
    errs[#errs + 1] = ("designer says %d blocks, independent count is %d"):format(c.py_total, expected)
  end
  if T.x ~= 0 or T.y ~= 0 or T.z ~= 0 or T.f ~= 0 then
    errs[#errs + 1] = ("turtle ended at %d,%d,%d f=%d"):format(T.x, T.y, T.z, T.f)
  end
  for k in pairs(visited) do
    local x, y, z = k:match("(-?%d+),(-?%d+),(-?%d+)")
    local gx, gy, gz = tonumber(x) + c.tx, tonumber(y) + c.ty, tonumber(z) + c.tz
    if gx < 1 or gx > c.w or gy < 1 or gy > c.h or gz < 1 or gz > c.d then
      errs[#errs + 1] = "WALKED OUTSIDE GRID " .. k
    end
  end
  local stored = itemCheck(errs)
  for _, n in ipairs({ "carve.job", "carve.pos", "carve.mined", "startup.lua" }) do
    if files[n] then errs[#errs + 1] = n .. " not cleaned up" end
  end
  return finishLine(c, errs, ("blocks %4d  fuel left %5s  actions %6d  in chest %4d"):format(
    expected, tostring(fuel), actions, stored))
end

local function load(c, ...)
  local f = assert(loadfile(CASES_DIR .. "/" .. c.file))
  return f(...)
end

local function plain(ex)
  ex.setJob(ex.planJob())
  ex.startRun((ex.buildRun()))
end

local function interrupt(c, ex, cuts)
  plain_started = true
  abortAfter = cuts[1]
  plain(ex)
  local n = 1
  for i = 2, #cuts do
    if not files["carve.job"] then break end
    abortAfter = actions + cuts[i]
    ex.resumeJob()
    n = n + 1
  end
  return n
end

local allOk = true
local function check(ok) allOk = allOk and ok end

local cases = dofile(CASES_DIR .. "/cases.lua")
for _, c in ipairs(cases) do
  resetTurtle(c)
  buildWorld(c)
  local ex = load(c, table.unpack(c.args or {}))
  local kind = c.kind or "plain"

  if kind == "plain" then
    plain(ex)
    check(verifyDone(c))

  elseif kind == "interrupt" then
    local n = interrupt(c, ex, c.cuts)
    if files["carve.job"] then ex.resumeJob() end
    c.name = c.name .. (" (%d interruptions)"):format(n)
    check(verifyDone(c))

  elseif kind == "main" then              -- the real start-up screen, Enter to begin
    events = { { "key", keys.enter } }
    ex.main()
    check(verifyDone(c))

  elseif kind == "cancel" then            -- any other key cancels, nothing is touched
    events = { { "key", keys.x } }
    ex.main()
    local errs = {}
    if digCount ~= 0 or actions ~= 0 then errs[#errs + 1] = "cancel still did something" end
    if files["carve.job"] or files["startup.lua"] then errs[#errs + 1] = "cancel left files behind" end
    check(finishLine(c, errs))

  elseif kind == "menu_resume" or kind == "menu_discard" or kind == "resume_arg" then
    interrupt(c, ex, { 400 })
    if not files["carve.job"] then
      check(finishLine(c, { "job finished before the interruption" }))
    else
      if kind == "menu_resume" then
        events = { { "key", keys.enter } }
        ex.main()
      elseif kind == "menu_discard" then
        T = { x = 0, y = 0, z = 0, f = 0 }      -- the player carries the turtle back to the start
        events = { { "key", keys.d }, { "key", keys.enter } }
        ex.main()
      else
        local ex2 = load(c, "resume")
        events = {}
        for i = 1, 5 do events[i] = { "timer", 1 } end
        ex2.main()
      end
      check(verifyDone(c))
    end

  elseif kind == "no_tool" then
    plain(ex)
    local errs = {}
    local said = table.concat(OUT, "\n", OUT_START + 1):find("no digging tool", 1, true)
    if not said then errs[#errs + 1] = "no clear 'equip a pickaxe' message" end
    if sleepCount > 20 or actions > 200 then errs[#errs + 1] = "kept hammering without a tool" end
    if files["startup.lua"] then errs[#errs + 1] = "startup.lua left behind" end
    check(finishLine(c, errs, ("actions %d sleeps %d"):format(actions, sleepCount)))

  elseif kind == "no_chest_wait" then     -- chest wanted but missing: wait, never litter
    plain(ex)
    local errs = {}
    if droppedGround ~= 0 then errs[#errs + 1] = "dropped items on the ground" end
    if not files["carve.job"] then errs[#errs + 1] = "job should still be pending" end
    check(finishLine(c, errs, "waited for a chest"))

  elseif kind == "perf" then
    local t0 = os.clock()
    plain(ex)
    local secs = os.clock() - t0
    c.name = c.name .. (" [%.1fs sim]"):format(secs)
    check(verifyDone(c))
  end
end

log(allOk and "\nALL ENGINE TESTS PASSED" or "\nSOME ENGINE TESTS FAILED")
return table.concat(OUT, "\n")
