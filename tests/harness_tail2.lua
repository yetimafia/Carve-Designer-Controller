---------------------------------------------------------------- test scaffolding
local function id(c, x, y, z) return ((y - 1) * c.d + (z - 1)) * c.w + x end
local initial

local function resetTurtle(c)
  T = { x = 0, y = 0, z = 0, f = 0 }
  fuel, inv, selSlot = c.fuel or 2000, {}, 1
  fuelUnlimited = c.unlimited or false
  noTool = c.noTool or false
  itemKinds = c.kinds or 18
  NOCOAL, COBBLE = c.nocoal or false, c.cobble or false
  burned, initialItems = 0, c.coal or 0
  if (c.coal or 0) > 0 then inv[16] = { name = "minecraft:coal", count = c.coal } end
  placedCount = 0
  CUR = c
  PRINTED = {}
  REFILL = c.refill
  for s, it in pairs(c.supply or {}) do
    inv[tonumber(s)] = { name = it[1], count = it[2] }
    initialItems = initialItems + it[2]
  end
  chestStore, lost, droppedGround, digCount, actions = {}, 0, 0, 0, 0
  if (c.chestCoal or 0) > 0 then
    chestStore["minecraft:coal"] = c.chestCoal
    initialItems = initialItems + c.chestCoal
  end
  abortAfter, visited, chestDug = nil, {}, false
  sleepCount = 0
  files = {}
  events = {}
  evlog = nil
  HTTP_POSTS, HTTP_BLOCK, HTTP_FAIL = {}, c.httpBlock or false, c.httpFail or false
  HTTP_STOP_AFTER, TERM_PENDING = c.stopAfter, false
  OUT_START = #OUT
end

local function buildWorld(c)
  W = {}
  TA = {}
  TORCH_POPS, TORCH_PLACED, TORCH_SIDE = 0, 0, 0
  local special = {}
  for _, s in ipairs(c.special or {}) do special[id(c, s[1], s[2], s[3])] = s[4] end
  for y = 1, c.h do for z = 1, c.d do for x = 1, c.w do
    W[key(x - c.tx, y - c.ty, z - c.tz)] = special[id(c, x, y, z)] or "stone"
  end end end
  for z = 1, c.d do for x = 1, c.w do
    W[key(x - c.tx, -c.ty, z - c.tz)] = "floor"          -- solid ground under the design
  end end
  W[key(0, 0, 0)] = nil
  if c.worldChest then W[key(0, 0, -1)] = "chest" end
  for _, e in ipairs(c.extra or {}) do W[key(e[1] - c.tx, e[2] - c.ty, e[3] - c.tz)] = e[4] end
  initial = {}
  for k, v in pairs(W) do initial[k] = v end
end

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
  if held + stored + droppedGround + lost + burned + placedCount ~= digCount + initialItems then
    errs[#errs + 1] = ("item leak: held %d stored %d ground %d lost %d burned %d dug %d start %d"):format(
      held, stored, droppedGround, lost, burned, digCount, initialItems)
  end
  if lost > 0 then errs[#errs + 1] = "items lost (inventory overflow): " .. lost end
  if droppedGround > 0 then errs[#errs + 1] = "items dropped on the ground: " .. droppedGround end
  if chestDug then errs[#errs + 1] = "CHEST WAS DUG" end
  if (TORCH_SIDE or 0) > 0 then errs[#errs + 1] = "torches were placed on the side of a block: " .. TORCH_SIDE end
  if (TORCH_POPS or 0) > 0 then errs[#errs + 1] = "torches fell off when their block was broken: " .. TORCH_POPS end
  for _, name in pairs(CUR.inv or {}) do
    if chestStore[name] then errs[#errs + 1] = "supply items were dumped into the chest: " .. name end
  end
  return stored
end

local function finishLine(c, errs, extra)
  log(("%-44s %s %s"):format(c.name, #errs == 0 and "PASS" or "FAIL", extra or ""))
  for i = 1, math.min(#errs, 6) do log("    " .. errs[i]) end
  return #errs == 0
end

local function placeWant(c, x, y, z)
  if not c.place then return nil end
  local ch = c.place[y]:sub((z - 1) * c.w + x, (z - 1) * c.w + x)
  local sl = tonumber(ch, 17)
  if sl and sl >= 1 then return (c.inv[tostring(sl)] or c.inv[sl]):gsub("^minecraft:", "") end
  return nil
end

local function verifyDone(c)
  local errs = {}
  local reach = expectedReach(c)
  local expected = 0
  for y = 1, c.h do for z = 1, c.d do for x = 1, c.w do
    local k = key(x - c.tx, y - c.ty, z - c.tz)
    local want = placeWant(c, x, y, z)
    if reach[id(c, x, y, z)] and initial[k] == "stone" and want and not (x == c.tx and y == c.ty and z == c.tz) then
      expected = expected + 1
      if W[k] ~= want and not (c.allowFail and W[k] == nil) then
        errs[#errs + 1] = "NOT PLACED " .. k .. " want " .. want .. " got " .. tostring(W[k])
      end
    elseif reach[id(c, x, y, z)] and initial[k] == "stone" then
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

local function interrupt(ex, cuts)
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

local baseSleep = sleep
sleep = function(n)
  if REFILL then                                  -- somebody tops up the turtle while it waits
    local it = inv[REFILL.slot]
    if it and it.name == REFILL.name then
      it.count = it.count + REFILL.count
    else
      inv[REFILL.slot] = { name = REFILL.name, count = REFILL.count }
    end
    initialItems = initialItems + REFILL.count
    REFILL = nil
  end
  return baseSleep(n)
end

local allOk = true
local function check(ok) allOk = allOk and ok end

local function dumpPosts(c)
  if c.live then
    for _, body in ipairs(HTTP_POSTS) do log("HTTP:" .. c.key .. "|" .. body) end
  end
end

local cases = dofile(CASES_DIR .. "/cases.lua")
for _, c in ipairs(cases) do
  c.key = c.name
  resetTurtle(c)
  buildWorld(c)
  local kind = c.kind or "plain"
  local ex = kind ~= "launcher" and load(c, table.unpack(c.args or {})) or nil

  if kind == "plain" then
    plain(ex)
    check(verifyDone(c))

  elseif kind == "path" then              -- record every turn / dig / move for comparison with the app's simulator
    evlog = {}
    plain(ex)
    log("EVENTS:" .. c.name .. "|" .. table.concat(evlog, ";"))
    evlog = nil
    check(verifyDone(c))

  elseif kind == "interrupt" then
    local n = interrupt(ex, c.cuts)
    if files["carve.job"] then ex.resumeJob() end
    c.name = c.name .. (" (%d interruptions)"):format(n)
    check(verifyDone(c))

  elseif kind == "main" then
    events = { { "key", keys.enter } }
    ex.main()
    check(verifyDone(c))

  elseif kind == "cancel" then
    events = { { "key", keys.x } }
    if c.dump then dumpAt[pulls + 1] = "SCREEN:" .. c.name end
    ex.main()
    local errs = {}
    if digCount ~= 0 or actions ~= 0 then errs[#errs + 1] = "cancel still did something" end
    if files["carve.job"] or files["startup.lua"] then errs[#errs + 1] = "cancel left files behind" end
    check(finishLine(c, errs))

  elseif kind == "menu_resume" or kind == "menu_discard" or kind == "resume_arg" then
    interrupt(ex, { 400 })
    if not files["carve.job"] then
      check(finishLine(c, { "job finished before the interruption" }))
    else
      if kind == "menu_resume" then
        events = { { "key", keys.enter } }
        ex.main()
      elseif kind == "menu_discard" then
        T = { x = 0, y = 0, z = 0, f = 0 }
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

  elseif kind == "no_chest_wait" then
    plain(ex)
    local errs = {}
    if droppedGround ~= 0 then errs[#errs + 1] = "dropped items on the ground" end
    if not files["carve.job"] then errs[#errs + 1] = "job should still be pending" end
    check(finishLine(c, errs, "waited for a chest"))

  elseif kind == "no_supply" then
    plain(ex)
    local errs = {}
    local said = table.concat(PRINTED, "\n"):find("Out of minecraft:torch", 1, true)
    if not said then errs[#errs + 1] = "never asked for torches" end
    if not table.concat(PRINTED, "\n"):find("more in slot 16", 1, true) then errs[#errs + 1] = "message does not say how many are needed" end
    if not files["carve.job"] then errs[#errs + 1] = "job should still be waiting" end
    if digCount == 0 then errs[#errs + 1] = "should have dug everything first" end
    if droppedGround ~= 0 then errs[#errs + 1] = "dropped items on the ground" end
    local seenTorch = false
    for _, b in pairs(W) do if b == "torch" then seenTorch = true end end
    if seenTorch then errs[#errs + 1] = "placed a torch from nowhere" end
    check(finishLine(c, errs, "waited for torches"))

  elseif kind == "seal" then              -- lava/water above and below get plugged (or are left alone when sealing is off)
    plain(ex)
    local errs = {}
    for _, w in ipairs(c.watch or {}) do
      local k = key(w[1] - c.tx, w[2] - c.ty, w[3] - c.tz)
      local want = c.expectSealed and "cobblestone" or initial[k]
      if W[k] ~= want then errs[#errs + 1] = ("%s is %s, expected %s"):format(k, tostring(W[k]), tostring(want)) end
    end
    check(finishLine(c, errs, "plugged") and verifyDone(c))

  elseif kind == "chest_fuel" then        -- out of fuel with coal waiting in the chest
    plain(ex)
    local errs = {}
    if burned == 0 then errs[#errs + 1] = "never used the chest coal" end
    check(finishLine(c, errs, ("burned %d"):format(burned)) and verifyDone(c))

  elseif kind == "chest_fuel_untouched" then
    plain(ex)
    local errs = {}
    if burned ~= 0 or (chestStore["minecraft:coal"] or 0) ~= c.chestCoal then errs[#errs + 1] = "took coal it did not need" end
    check(finishLine(c, errs) and verifyDone(c))

  elseif kind == "perf" then
    plain(ex)
    check(verifyDone(c))

  elseif kind == "live_stop" then         -- the Fleet page answers "stop": the program must end like Ctrl+T
    events = { { "key", keys.enter } }
    local ok, err = pcall(ex.main)
    local errs = {}
    if not tostring(HTTP_POSTS[#HTTP_POSTS]):find('"stopped":true', 1, true) then errs[#errs + 1] = "last report is not a Stopped one" end
    if #HTTP_POSTS > c.stopAfter + 6 then errs[#errs + 1] = "kept sending reports: " .. #HTTP_POSTS end
    if digCount >= c.py_total then errs[#errs + 1] = "dug everything anyway" end
    check(finishLine(c, errs, #HTTP_POSTS .. " posts, " .. digCount .. " dug"))

  elseif kind == "live_off" then          -- reporting blocked / app unreachable / http missing: job must still finish
    local saved = http
    if c.noHttp then http = nil end
    plain(ex)
    http = saved
    local errs = {}
    if c.noHttp or c.httpBlock then
      if #HTTP_POSTS ~= 0 then errs[#errs + 1] = "posted although blocked" end
    end
    if c.httpFail and #HTTP_POSTS ~= 0 then errs[#errs + 1] = "unexpected posts" end
    local ok = finishLine(c, errs)
    check(ok and verifyDone(c))

  elseif kind == "launcher" then
    HTTP_BASE, HTTP_FILES = c.base, c.files
    for k, v in pairs(c.preFiles or {}) do files[k] = v end
    SHELL_RUNS, PRINTED = {}, {}
    readQueue = {}
    for _, a in ipairs(c.answers or {}) do readQueue[#readQueue + 1] = a end
    local f = assert(loadfile(CASES_DIR .. "/" .. c.file))
    local okRun, err = pcall(f, table.unpack(c.args or {}))
    local errs = {}
    if c.expectError then
      if okRun then errs[#errs + 1] = "expected an error" end
      if not tostring(err):find(c.expectError, 1, true) then errs[#errs + 1] = "error was: " .. tostring(err) end
    elseif not okRun then
      errs[#errs + 1] = "failed: " .. tostring(err)
    end
    if c.expectRun then
      if SHELL_RUNS[1] ~= c.expectRun then errs[#errs + 1] = "ran: " .. tostring(SHELL_RUNS[1]) end
      if c.expectFile and files[c.expectFile[1]] ~= c.expectFile[2] then errs[#errs + 1] = "downloaded file differs" end
    elseif #SHELL_RUNS > 0 then
      errs[#errs + 1] = "should not have run anything: " .. SHELL_RUNS[1]
    end
    if c.expectPrint and not table.concat(PRINTED, "\n"):find(c.expectPrint, 1, true) then
      errs[#errs + 1] = "output lacks: " .. c.expectPrint
    end
    check(finishLine(c, errs))
  end
  dumpPosts(c)
end

log(allOk and "\nALL ENGINE TESTS PASSED" or "\nSOME ENGINE TESTS FAILED")
return table.concat(OUT, "\n")
