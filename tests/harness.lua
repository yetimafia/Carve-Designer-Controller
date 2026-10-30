-- Test harness: fake CC:Tweaked environment + simulated turtle world
CARVE_TEST = true
local CASES_DIR = rawget(_G, "CASES_DIR") or "."
local OUT = {}
PRINTED = {}
OUT_START = 0
local function log(...)
  local t = {}
  for i = 1, select("#", ...) do t[#t + 1] = tostring((select(i, ...))) end
  OUT[#OUT + 1] = table.concat(t, " ")
end

---------------------------------------------------------------- mock OS bits
local files = {}
fs = {
  exists = function(n) return files[n] ~= nil end,
  open = function(n, mode)
    if mode == "w" then
      local buf = {}
      return { write = function(s) buf[#buf + 1] = s end,
               close = function() files[n] = table.concat(buf) end }
    end
    if files[n] == nil then return nil end
    return { readAll = function() return files[n] end, close = function() end }
  end,
  delete = function(n) files[n] = nil end,
}

textutils = {
  unserialiseJSON = function(s) return PY_JSON(s) end,
  serialise = function(t)
    local function ser(v)
      if type(v) == "string" then return string.format("%q", v) end
      if type(v) ~= "table" then return tostring(v) end
      local parts = {}
      local n = #v
      for i = 1, n do parts[#parts + 1] = ser(v[i]) end
      for k, x in pairs(v) do
        if not (type(k) == "number" and k >= 1 and k <= n and math.floor(k) == k) then
          local key = type(k) == "string" and k:match("^[%a_][%w_]*$") and k or "[" .. ser(k) .. "]"
          parts[#parts + 1] = key .. "=" .. ser(x)
        end
      end
      return "{" .. table.concat(parts, ",") .. "}"
    end
    return ser(t)
  end,
  unserialise = function(s)
    local f = load("return " .. s)
    if not f then return nil end
    local ok, r = pcall(f)
    if ok then return r end
  end,
}

local names = { "white", "orange", "magenta", "lightBlue", "yellow", "lime", "pink", "gray",
                "lightGray", "cyan", "purple", "blue", "brown", "green", "red", "black" }
colors = {}
for i, n in ipairs(names) do colors[n] = 1 << (i - 1) end
colors.toBlit = function(c)
  for i, n in ipairs(names) do if colors[n] == c then return string.format("%x", i - 1) end end
  error("bad color " .. tostring(c))
end
keys = { enter = 28, d = 32, x = 45 }
SHELL_RUNS = {}
shell = { getRunningProgram = function() return "carve" end,
          run = function(...) SHELL_RUNS[#SHELL_RUNS + 1] = table.concat({ ... }, " "); return true end }
HTTP_POSTS, HTTP_FILES, HTTP_BLOCK, HTTP_BASE, HTTP_FAIL = {}, {}, false, "", false
http = {
  request = function(t)
    if HTTP_FAIL then return false, "connection refused" end
    HTTP_POSTS[#HTTP_POSTS + 1] = t.body
    return true
  end,
  post = function(t)
    if HTTP_FAIL then return nil, "connection refused" end
    HTTP_POSTS[#HTTP_POSTS + 1] = t.body
    local reply = (HTTP_STOP_AFTER and #HTTP_POSTS >= HTTP_STOP_AFTER) and "ok stop" or "ok"
    return { readAll = function() return reply end, close = function() end }
  end,
  checkURL = function(u)
    if HTTP_BLOCK then return false, "Domain not permitted" end
    return true
  end,
  get = function(url)
    local path = url:match("^" .. HTTP_BASE:gsub("%p", "%%%0") .. "/(.-)%?nocache=")
    if not path or HTTP_FILES[path] == nil then return nil, "404" end
    local body = HTTP_FILES[path]
    return { readAll = function() return body end, close = function() end }
  end,
}
os.getComputerID = function() return 7 end
os.queueEvent = function(e) if e == "terminate" then TERM_PENDING = true end end
os.getComputerLabel = function() return nil end
os.epoch = function() return 1700000000000 end
write = function(s) term.write(s) end
printError = function(...) log("ERR:", ...) end

local sleepCount = 0
local fakeTime = 0
os.clock = function() return fakeTime end
sleep = function(n) fakeTime = fakeTime + (n or 1); sleepCount = sleepCount + 1; if sleepCount > 5000 then error("too many sleeps " .. debug.traceback(), 0) end end

-- terminal with a real character buffer so we can look at the GUI
local SW, SH = 39, 13
local screen, cx, cy = {}, 1, 1
local function clr() for y = 1, SH do screen[y] = string.rep(" ", SW) end end
clr()
term = {
  getSize = function() return SW, SH end,
  isColor = function() return true end,
  clear = clr,
  setCursorPos = function(x, y) cx, cy = x, y end,
  write = function(s)
    s = tostring(s)
    local row = screen[cy]
    if row then screen[cy] = (row:sub(1, cx - 1) .. s .. row:sub(cx + #s)):sub(1, SW) end
    cx = cx + #s
  end,
  blit = function(t, f, b)
    assert(#t == #f and #t == #b, "blit length mismatch")
    term.write(t)
  end,
  setBackgroundColor = function() end,
  setTextColor = function() end,
}
print = function(...)
  local t = {}
  for i = 1, select("#", ...) do t[#t + 1] = tostring((select(i, ...))) end
  PRINTED[#PRINTED + 1] = table.concat(t, " ")
  term.write(table.concat(t, " "))
  cx, cy = 1, cy + 1
end
local function dumpScreen(title)
  log("---- " .. title)
  for y = 1, SH do log("|" .. screen[y] .. "|") end
end

local events, pulls, dumpAt = {}, 0, {}
os.pullEvent = function()
  pulls = pulls + 1
  if dumpAt[pulls] then dumpScreen(dumpAt[pulls]) end
  local e = table.remove(events, 1)
  if not e then error("event queue empty", 0) end
  return table.unpack(e)
end
os.startTimer = function() return 1 end
local readQueue = {}
read = function()
  if #readQueue == 0 then error("read queue empty", 0) end
  return table.remove(readQueue, 1)
end

---------------------------------------------------------------- simulated turtle
local W, T, fuel, inv, selSlot
local TA = {}                       -- torch cell -> the block it hangs on / stands on
local chestStore, lost, droppedGround, digCount, actions, abortAfter, visited, chestDug
local fuelUnlimited = false
local noTool = false
local evlog, itemKinds = nil, 18
local burned, initialItems = 0, 0
local FWD = { { 0, 1 }, { 1, 0 }, { 0, -1 }, { -1, 0 } }
local function key(x, y, z) return x .. "," .. y .. "," .. z end

local function bump()
  actions = actions + 1
  fakeTime = fakeTime + 0.4
  if abortAfter and actions >= abortAfter then abortAfter = nil; error("Terminated", 0) end
  if TERM_PENDING then TERM_PENDING = false; error("Terminated", 0) end
end
local function tgt(dir)
  if dir == "u" then return T.x, T.y + 1, T.z end
  if dir == "d" then return T.x, T.y - 1, T.z end
  local v = FWD[T.f + 1]
  return T.x + v[1], T.y, T.z + v[2]
end
local function blockAt(dir) local x, y, z = tgt(dir); return W[key(x, y, z)] end
local function addItem(name)
  for i = 1, 16 do
    if inv[i] and inv[i].name == name and inv[i].count < 64 then inv[i].count = inv[i].count + 1; return end
  end
  for i = 1, 16 do
    if not inv[i] then inv[i] = { name = name, count = 1 }; return end
  end
  lost = lost + 1
end
local function itemFor(x, y, z)
  local h = (x * 7 + y * 13 + z * 29) % itemKinds
  if h == 0 and not NOCOAL then return "minecraft:coal" end
  if h == 2 and COBBLE then return "minecraft:cobblestone" end
  return "minecraft:item_" .. h
end

turtle = {}
local function mkDetect(dir) return function() bump(); return blockAt(dir) ~= nil end end
local function mkInspect(dir)
  return function()
    bump()
    local b = blockAt(dir)
    if b then return true, { name = "minecraft:" .. b } end
    return false, "No block to inspect"
  end
end
local function mkDig(dir)
  return function()
    bump()
    if noTool then return false, "No tool to dig with" end
    local x, y, z = tgt(dir)
    local b = W[key(x, y, z)]
    if not b then return false, "Nothing to dig here" end
    if b == "bedrock" then return false, "Unbreakable block detected" end
    if b == "water" then return false, "Cannot break block with this tool" end
    if b == "chest" then chestDug = true end
    W[key(x, y, z)] = nil
    addItem(itemFor(x, y, z))
    digCount = digCount + 1
    if evlog then evlog[#evlog + 1] = ("d,%d,%d,%d"):format(x, y, z) end
    local me = key(x, y, z)
    for tk, support in pairs(TA) do           -- a torch loses its block: it pops off as an item
      if support == me then
        W[tk] = nil
        TA[tk] = nil
        droppedGround = droppedGround + 1
        TORCH_POPS = (TORCH_POPS or 0) + 1
      end
    end
    return true
  end
end
local function mkMove(dir)
  return function()
    bump()
    if not fuelUnlimited and fuel <= 0 then return false, "Out of fuel" end
    local x, y, z = tgt(dir)
    local b = W[key(x, y, z)]
    if b and b ~= "water" and b ~= "lava" then return false, "Movement obstructed" end
    T.x, T.y, T.z = x, y, z
    if evlog then evlog[#evlog + 1] = ("m,%d,%d,%d"):format(x, y, z) end
    fuel = fuel - 1
    visited[key(x, y, z)] = true
    return true
  end
end
turtle.detect, turtle.detectUp, turtle.detectDown = mkDetect("f"), mkDetect("u"), mkDetect("d")
turtle.inspect, turtle.inspectUp, turtle.inspectDown = mkInspect("f"), mkInspect("u"), mkInspect("d")
turtle.dig, turtle.digUp, turtle.digDown = mkDig("f"), mkDig("u"), mkDig("d")
turtle.forward, turtle.up, turtle.down = mkMove("f"), mkMove("u"), mkMove("d")
turtle.suck = function()
  bump()
  if blockAt("f") ~= "chest" then return false, "No items to take" end
  local names = {}
  for k in pairs(chestStore) do names[#names + 1] = k end
  table.sort(names)
  if #names == 0 then return false, "No items to take" end
  local nm = names[1]
  local n = math.min(64, chestStore[nm])
  chestStore[nm] = chestStore[nm] - n
  if chestStore[nm] == 0 then chestStore[nm] = nil end
  for _ = 1, n do addItem(nm) end
  return true
end
turtle.attack = function() bump(); return false end
turtle.attackUp, turtle.attackDown = turtle.attack, turtle.attack
turtle.turnRight = function() bump(); T.f = (T.f + 1) % 4; if evlog then evlog[#evlog + 1] = "t," .. (T.f + 1) end; return true end
turtle.turnLeft = function() bump(); T.f = (T.f + 3) % 4; if evlog then evlog[#evlog + 1] = "t," .. (T.f + 1) end; return true end
turtle.select = function(s) selSlot = s; return true end
turtle.getItemCount = function(s) return inv[s] and inv[s].count or 0 end
turtle.getFuelLevel = function() return fuelUnlimited and "unlimited" or fuel end
turtle.getFuelLimit = function() return 20000 end
turtle.drop = function()
  bump()
  local it = inv[selSlot]
  if not it then return false, "No items to drop" end
  if blockAt("f") == "chest" then
    chestStore[it.name] = (chestStore[it.name] or 0) + it.count
  else
    droppedGround = droppedGround + it.count
  end
  inv[selSlot] = nil
  return true
end
local placedCount = 0
turtle.getItemDetail = function(s)
  local it = inv[s]
  if not it then return nil end
  return { name = it.name, count = it.count }
end
local SUPPORT_DIRS = { { 1, 0, 0 }, { -1, 0, 0 }, { 0, 1, 0 }, { 0, -1, 0 }, { 0, 0, 1 }, { 0, 0, -1 } }
local function supported(x, y, z)
  for _, d in ipairs(SUPPORT_DIRS) do
    local b = W[key(x + d[1], y + d[2], z + d[3])]
    if b and b ~= "water" and b ~= "torch" then return true end
  end
  return false
end
local function mkPlace(dir)
  return function()
    bump()
    local it = inv[selSlot]
    if not it then return false, "No items to place" end
    local x, y, z = tgt(dir)
    local here = W[key(x, y, z)]
    if here and here ~= "water" and here ~= "lava" then return false, "Cannot place block here" end
    if it.name == "minecraft:torch" then
      -- like the real game: the torch hangs on the block behind the spot (a wall torch) or stands on the
      -- block under it; it cannot hang from the ceiling
      local sx, sy, sz
      if dir == "u" then return false, "Cannot place block here" end
      if dir == "d" then sx, sy, sz = x, y - 1, z
      else
        local v = FWD[T.f + 1]
        sx, sy, sz = x + v[1], y, z + v[2]
      end
      local sb = W[key(sx, sy, sz)]
      if not sb or sb == "water" or sb == "torch" then return false, "Cannot place block here" end
      TA[key(x, y, z)] = key(sx, sy, sz)
      TORCH_PLACED = (TORCH_PLACED or 0) + 1
      if dir == "f" then TORCH_SIDE = (TORCH_SIDE or 0) + 1 end
    end
    local nm = it.name:gsub("^minecraft:", "")
    W[key(x, y, z)] = nm
    it.count = it.count - 1
    if it.count == 0 then inv[selSlot] = nil end
    placedCount = placedCount + 1
    if evlog then evlog[#evlog + 1] = ("p,%d,%d,%d"):format(x, y, z) end
    return true
  end
end
turtle.place, turtle.placeUp, turtle.placeDown = mkPlace("f"), mkPlace("u"), mkPlace("d")
turtle.refuel = function(n)
  bump()
  local it = inv[selSlot]
  if not it then return false, "No items to combust" end
  if it.name ~= "minecraft:coal" then return false, "Items not combustible" end
  n = n or it.count
  if n == 0 then return true end
  local use = math.min(n, it.count)
  it.count = it.count - use
  burned = burned + use
  fuel = math.min(20000, fuel + 80 * use)
  if it.count == 0 then inv[selSlot] = nil end
  return true
end


if os.getenv and os.getenv("CARVE_TRACE") then
  local real_error = error
  error = function(m, l)
    log("TRACE:", debug.traceback(tostring(m), 2))
    real_error(m, l)
  end
end

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
