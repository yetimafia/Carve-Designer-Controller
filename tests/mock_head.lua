-- Test harness: fake CC:Tweaked environment + simulated turtle world
CARVE_TEST = true
local CASES_DIR = ...  or "."
local OUT = {}
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
shell = { getRunningProgram = function() return "carve" end }
printError = function(...) log("ERR:", ...) end

local sleepCount = 0
sleep = function() sleepCount = sleepCount + 1; if sleepCount > 5000 then error("too many sleeps", 0) end end

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
read = function() return table.remove(readQueue, 1) or "" end

---------------------------------------------------------------- simulated turtle
local W, T, fuel, inv, selSlot
local TA = {}                       -- torch cell -> the block it hangs on / stands on
local chestStore, lost, droppedGround, digCount, actions, abortAfter, visited, chestDug
local fuelUnlimited = false
local noTool = false
local burned, initialItems = 0, 0
local FWD = { { 0, 1 }, { 1, 0 }, { 0, -1 }, { -1, 0 } }
local function key(x, y, z) return x .. "," .. y .. "," .. z end

local function bump()
  actions = actions + 1
  if abortAfter and actions >= abortAfter then abortAfter = nil; error("Terminated", 0) end
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
  local h = (x * 7 + y * 13 + z * 29) % 18
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
turtle.turnRight = function() bump(); T.f = (T.f + 1) % 4; return true end
turtle.turnLeft = function() bump(); T.f = (T.f + 3) % 4; return true end
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
