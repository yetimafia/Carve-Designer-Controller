-- Mock CC:Tweaked world for the automation programs: blocks, containers, furnaces, trees, crafting.
local M = {}
CARVE_TEST = true
local function key(x, y, z) return x .. "," .. y .. "," .. z end
M.key = key

local files = {}
fs = {
  exists = function(n) return files[n] ~= nil end,
  open = function(n, mode)
    if mode == "w" then
      local buf = {}
      return { write = function(s) buf[#buf + 1] = s end, close = function() files[n] = table.concat(buf) end }
    end
    if files[n] == nil then return nil end
    return { readAll = function() return files[n] end, close = function() end }
  end,
  delete = function(n) files[n] = nil end,
}
M.files = files
local names = { "white", "orange", "magenta", "lightBlue", "yellow", "lime", "pink", "gray",
                "lightGray", "cyan", "purple", "blue", "brown", "green", "red", "black" }
colors = {}
for i, n in ipairs(names) do colors[n] = 1 << (i - 1) end
M.screen = {}
term = {
  setBackgroundColor = function() end, setTextColor = function() end, clear = function() M.screen = {} end,
  getSize = function() return 39, 13 end,
  setCursorPos = function(x, y) M.row = y end, write = function(s) M.screen[M.row or 1] = tostring(s) end,
}
M.shellRuns = {}
shell = { getRunningProgram = function() return "job_test" end,
          run = function(...) M.shellRuns[#M.shellRuns + 1] = table.concat({ ... }, " "); return true end }
printError = function(...) M.errors[#M.errors + 1] = table.concat({ ... }, " ") end

local W, T, inv, selSlot, fuel, now, ABORT, actions
local FWD = { { 0, 1 }, { 1, 0 }, { 0, -1 }, { -1, 0 } }
local STACK = 64
local BURN = { coal = 80, charcoal = 80, oak_log = 15, birch_log = 15, stick = 5, oak_planks = 15 }
local SMELT = { raw_iron = "iron_ingot", raw_gold = "gold_ingot", cobblestone = "stone", sand = "glass", beef = "cooked_beef",
                oak_log = "charcoal", raw_copper = "copper_ingot" }
M.RECIPES = {}
local function short(n) return (n or ""):gsub("^minecraft:", "") end

local function tgt(dir)
  if dir == "u" then return T.x, T.y + 1, T.z end
  if dir == "d" then return T.x, T.y - 1, T.z end
  local v = FWD[T.f + 1]
  return T.x + v[1], T.y, T.z + v[2]
end
local function at(dir) local x, y, z = tgt(dir); return W[key(x, y, z)], x, y, z end

local function addItem(name, count)
  count = count or 1
  for i = 1, 16 do
    if count == 0 then return 0 end
    if inv[i] and inv[i].name == name and inv[i].count < STACK then
      local n = math.min(count, STACK - inv[i].count); inv[i].count = inv[i].count + n; count = count - n
    end
  end
  for i = 1, 16 do
    if count == 0 then return 0 end
    if not inv[i] then
      local n = math.min(count, STACK); inv[i] = { name = name, count = n }; count = count - n
    end
  end
  M.lost = (M.lost or 0) + count
  return count
end
M.addItem = function(n, c) return addItem(n, c) end

local function bump()
  actions = actions + 1
  if ABORT and actions >= ABORT then ABORT = nil; error("Terminated", 0) end
  if M.termPending then M.termPending = false; error("Terminated", 0) end
end

-------------------------------------------------------------- containers
local function contAdd(b, name, count)            -- add to a chest-like list, returns leftover
  for _, st in ipairs(b.inv) do
    if st.name == name and st.count < STACK and count > 0 then
      local n = math.min(count, STACK - st.count); st.count = st.count + n; count = count - n
    end
  end
  while count > 0 and #b.inv < (b.size or 27) do
    local n = math.min(count, STACK); b.inv[#b.inv + 1] = { name = name, count = n }; count = count - n
  end
  return count
end
local function isFuel(name) return BURN[short(name)] ~= nil end

-- furnace: input / fuel / output. faces: "u" = top (input), "s" = side (fuel), "d" = bottom (output)
local function furnaceInsert(b, face, name, count)
  if face == "u" then
    if b.input and b.input.name ~= name then return 0 end
    local have = b.input and b.input.count or 0
    local n = math.min(count, STACK - have)
    if n > 0 then
      b.input = { name = name, count = have + n }
      if not SMELT[short(name)] then M.junkIn = (M.junkIn or 0) + n end
    end
    return n
  elseif face == "s" then
    if not isFuel(name) then return 0 end
    if b.fuel and b.fuel.name ~= name then return 0 end
    local have = b.fuel and b.fuel.count or 0
    local n = math.min(count, STACK - have)
    if n > 0 then b.fuel = { name = name, count = have + n } end
    return n
  end
  return 0
end
local function furnaceTick(b, secs)
  b.t = (b.t or 0) + secs
  while b.t >= 10 do
    if not (b.input and SMELT[short(b.input.name)]) then b.t = 0; return end
    if (b.credits or 0) <= 0 then
      if b.fuel and b.fuel.count > 0 then
        b.credits = (BURN[short(b.fuel.name)] or 0) / 10
        b.fuel.count = b.fuel.count - 1
        if b.fuel.count == 0 then b.fuel = nil end
      else b.t = 0; return end
    end
    local res = "minecraft:" .. SMELT[short(b.input.name)]
    if b.output and b.output.name ~= res then b.t = 0; return end
    b.output = { name = res, count = (b.output and b.output.count or 0) + 1 }
    b.input.count = b.input.count - 1
    if b.input.count == 0 then b.input = nil end
    b.credits = b.credits - 1
    b.t = b.t - 10
    M.smelted = (M.smelted or 0) + 1
  end
end

-------------------------------------------------------------- trees
local GROW = 900
local function growTree(x, y, z)
  W[key(x, y, z)] = nil
  for h = 0, 3 do W[key(x, y + h, z)] = { name = "minecraft:oak_log" } end
  for _, d in ipairs({ { 1, 0 }, { -1, 0 }, { 0, 1 }, { 0, -1 } }) do
    for h = 2, 3 do
      if not W[key(x + d[1], y + h, z + d[2])] then W[key(x + d[1], y + h, z + d[2])] = { name = "minecraft:oak_leaves" } end
    end
  end
  W[key(x, y + 4, z)] = { name = "minecraft:oak_leaves" }
  M.grown = (M.grown or 0) + 1
end
local function treeTick()
  local ready = {}
  for k, b in pairs(W) do
    if b.name == "minecraft:oak_sapling" and (now - b.planted >= GROW or (b.bone or 0) >= 3) then ready[#ready + 1] = k end
  end
  for _, k in ipairs(ready) do
    local x, y, z = k:match("(-?%d+),(-?%d+),(-?%d+)")
    growTree(tonumber(x), tonumber(y), tonumber(z))
  end
end

local function tick(secs)
  now = now + secs
  for _, b in pairs(W) do
    if b.name == "minecraft:furnace" then furnaceTick(b, secs) end
  end
  treeTick()
end

sleep = function(n)
  if M.termPending then M.termPending = false; error("Terminated", 0) end
  M.sleeps = (M.sleeps or 0) + 1
  if M.sleeps > 20000 then error("too many sleeps", 0) end
  tick(n or 1)
end

-------------------------------------------------------------- fleet reporting (http.post to the app)
M.posts, M.replyAfter = {}, nil
os.clock = function() return now or 0 end
os.getComputerID = function() return 5 end
M.label = "Lumber Jack"
os.getComputerLabel = function() return M.label end
os.setComputerLabel = function(l) M.label = l end
os.queueEvent = function(e) if e == "terminate" then M.termPending = true end end
http = {
  post = function(t)
    if M.httpDown then return nil, "connection refused" end
    if t.url:find("/map$") and (M.failMap or 0) > 0 then M.failMap = M.failMap - 1; return nil, "connection refused" end
    M.posts[#M.posts + 1] = { url = t.url, body = t.body }
    if t.url:find("/route$") then
      local text = M.routeText or ""
      return { readAll = function() return text end, close = function() end }
    end
    if t.url:find("/setup$") then
      if M.setupHandler then return { readAll = function() return M.setupHandler(t.body) end, close = function() end } end
      local reply = "ok"
      if M.setupReplies and #M.setupReplies > 0 then reply = table.remove(M.setupReplies, 1) end
      return { readAll = function() return reply end, close = function() end }
    end
    if t.url:find("/storage$") then
      local reply = "ok"
      if M.storageReplies and #M.storageReplies > 0 then reply = table.remove(M.storageReplies, 1) end
      return { readAll = function() return reply end, close = function() end }
    end
    local reply = (M.replyAfter and #M.posts >= M.replyAfter) and "ok stop" or "ok"
    if M.replyQueue and #M.replyQueue > 0 then reply = table.remove(M.replyQueue, 1) end
    if M.stopAfterRun and #M.shellRuns > 0 then reply = "ok stop" end
    return { readAll = function() return reply end, close = function() end }
  end,
}

-- peripheral.wrap("front" / "top" / "bottom"): a chest next to the turtle can list what it holds
peripheral = { getType = function(side)
  if M.workbenchSide == side then return "workbench" end
  return nil
end, wrap = function(side)
  if M.workbenchSide == side then return { craft = function(n) return turtle.craftReal(n) end } end
  if M.noPeripheral then return nil end
  local d = ({ front = "f", top = "u", bottom = "d" })[side]
  local b = d and at(d)
  if b and b.drive then
    return { isDiskPresent = function() return b.disk ~= nil end, getMountPath = function() return "disk" end }
  end
  if b and b.name == "computercraft:turtle_normal" then
    return { turnOn = function() b.on = true; M.booted = (M.booted or 0) + 1 end, getID = function() return b.id end,
             isOn = function() return b.on == true end }
  end
  if not b or not b.inv then return nil end
  return { size = function() return b.size or 27 end,
           list = function() local t = {}; for i, st in ipairs(b.inv) do t[i] = { name = st.name, count = st.count } end; return t end }
end }

-------------------------------------------------------------- the turtle
local function drops(b)
  local n = short(b.name)
  if n == "oak_leaves" then
    M.leaves = (M.leaves or 0) + 1
    if M.leaves % 3 == 0 then return "minecraft:oak_sapling" end
    return nil
  elseif n == "oak_sapling" then return "minecraft:oak_sapling"
  elseif n == "grass_block" then return "minecraft:dirt"
  elseif n == "stone" then return "minecraft:cobblestone"
  elseif n:find("_ore", 1, true) then
    local m = n:gsub("deepslate_", ""):gsub("_ore", "")
    if m == "iron" or m == "copper" or m == "gold" then return "minecraft:raw_" .. m end
    return "minecraft:" .. m
  end
  return b.name
end
turtle = {}
local function mk(dir)
  turtle["detect" .. (dir == "f" and "" or dir == "u" and "Up" or "Down")] = function() bump(); return at(dir) ~= nil end
  turtle["inspect" .. (dir == "f" and "" or dir == "u" and "Up" or "Down")] = function()
    bump()
    local b = at(dir)
    if not b then return false, "No block to inspect" end
    return true, { name = b.name }
  end
  turtle["dig" .. (dir == "f" and "" or dir == "u" and "Up" or "Down")] = function()
    bump()
    local b, x, y, z = at(dir)
    if not b then return false, "Nothing to dig here" end
    if b.name == "minecraft:bedrock" then return false, "Unbreakable block detected" end
    if b.name == "minecraft:furnace" or b.name == "minecraft:chest" then M.dugProtected = (M.dugProtected or 0) + 1 end
    W[key(x, y, z)] = nil
    local d = drops(b)
    if d then addItem(d, 1) end
    if short(b.name) == "oak_log" then               -- leaves that decay drop saplings; assume the turtle picks up half of them
      M.logs = (M.logs or 0) + 1
      if M.logs % 2 == 0 then addItem("minecraft:oak_sapling", 1) end
    end
    M.digs = (M.digs or 0) + 1
    return true
  end
  turtle[dir == "f" and "forward" or dir == "u" and "up" or "down"] = function()
    bump()
    if fuel <= 0 then return false, "Out of fuel" end
    local b, x, y, z = at(dir)
    if b then return false, "Movement obstructed" end
    if M.noGround == nil and y < M.minY then return false, "Movement obstructed" end
    T.x, T.y, T.z = x, y, z
    fuel = fuel - 1
    M.moves = (M.moves or 0) + 1
    tick(0.4)
    return true
  end
  turtle["attack" .. (dir == "f" and "" or dir == "u" and "Up" or "Down")] = function() bump(); return false end
end
mk("f"); mk("u"); mk("d")
turtle.turnRight = function() bump(); T.f = (T.f + 1) % 4; return true end
turtle.turnLeft = function() bump(); T.f = (T.f + 3) % 4; return true end
turtle.select = function(s) selSlot = s; return true end
turtle.getItemCount = function(s) return inv[s] and inv[s].count or 0 end
turtle.getItemDetail = function(s) local it = inv[s]; if not it then return nil end; return { name = it.name, count = it.count } end
turtle.getFuelLevel = function() return fuel end
turtle.getFuelLimit = function() return 20000 end
turtle.transferTo = function(dest, n)
  bump()
  local a = inv[selSlot]
  if not a then return false end
  n = math.min(n or a.count, a.count)
  local b = inv[dest]
  if b and b.name ~= a.name then return false end
  if b then n = math.min(n, STACK - b.count) end
  if n <= 0 then return false end
  if b then b.count = b.count + n else inv[dest] = { name = a.name, count = n } end
  a.count = a.count - n
  if a.count == 0 then inv[selSlot] = nil end
  return true
end
turtle.refuel = function(n)
  bump()
  local it = inv[selSlot]
  if not it then return false, "No items to combust" end
  local v = BURN[short(it.name)]
  if not v then return false, "Items not combustible" end
  n = n or it.count
  if n == 0 then return true end
  local use = math.min(n, it.count)
  it.count = it.count - use
  fuel = math.min(20000, fuel + v * use)
  M.burned = (M.burned or 0) + use
  if it.count == 0 then inv[selSlot] = nil end
  return true
end

local function faceFor(dir)        -- which furnace face the turtle touches
  if dir == "d" then return "u" end        -- turtle above the furnace -> top
  if dir == "u" then return "d" end        -- turtle below -> bottom
  return "s"
end
local function dropTo(dir, count)
  bump()
  local it = inv[selSlot]
  if not it then return false, "No items to drop" end
  local b, bx, by, bz = at(dir)
  count = math.min(count or it.count, it.count)
  if b and b.hopper then                                         -- a hopper above a disk drive feeds it
    local below = W[key(bx, by - 1, bz)]
    if it.name == "computercraft:disk" and below and below.drive and not below.disk then
      below.disk = it.name
      it.count = it.count - 1
      if it.count == 0 then inv[selSlot] = nil end
      return true
    end
    local left = contAdd(b, it.name, count)
    if count - left == 0 then return false, "No space for items" end
    it.count = it.count - (count - left)
    if it.count == 0 then inv[selSlot] = nil end
    return true
  end
  if not b then
    M.ground = (M.ground or 0) + count
    it.count = it.count - count
  elseif b.drive and (M.driveNoDrop or (M.driveTopOnly and dir ~= "d")) then                          -- this pack's drive is not an inventory: the item lands on the ground
    M.ground = (M.ground or 0) + count
    it.count = it.count - count
  elseif b.drive then
    if b.disk or it.name ~= "computercraft:disk" then return false, "No space for items" end
    b.disk = it.name
    it.count = it.count - 1
  elseif b.inv then
    local left = contAdd(b, it.name, count)
    local moved = count - left
    if moved == 0 then return false, "No space for items" end
    it.count = it.count - moved
  elseif b.name == "minecraft:furnace" then
    local moved = furnaceInsert(b, faceFor(dir), it.name, count)
    if moved == 0 then return false, "No space for items" end
    it.count = it.count - moved
  else
    M.ground = (M.ground or 0) + count
    it.count = it.count - count
  end
  if it.count == 0 then inv[selSlot] = nil end
  return true
end
turtle.drop = function(n) return dropTo("f", n) end
turtle.dropUp = function(n) return dropTo("u", n) end
turtle.dropDown = function(n) return dropTo("d", n) end
local function suckFrom(dir, count)
  bump()
  local b = at(dir)
  if not b then return false, "No items to take" end
  if b.drive then
    if not b.disk then return false, "No items to take" end
    addItem(b.disk, 1); b.disk = nil
    return true
  end
  if b.inv then
    local st = b.inv[1]
    if not st then return false, "No items to take" end
    local n = math.min(count or st.count, st.count)
    local left = addItem(st.name, n)
    local taken = n - left
    if taken == 0 then return false, "No space" end
    st.count = st.count - taken
    if st.count == 0 then table.remove(b.inv, 1) end
    return true
  elseif b.name == "minecraft:furnace" and dir == "u" then       -- turtle below: only the output
    if not b.output then return false, "No items to take" end
    local n = b.output.count
    local left = addItem(b.output.name, n)
    local taken = n - left
    if taken == 0 then return false, "No space" end
    b.output.count = b.output.count - taken
    if b.output.count == 0 then b.output = nil end
    return true
  end
  return false, "No items to take"
end
turtle.suck = function(n) return suckFrom("f", n) end
turtle.suckUp = function(n) return suckFrom("u", n) end
turtle.suckDown = function(n) return suckFrom("d", n) end

turtle.place = nil
local function placeDir(dir)
  bump()
  local it = inv[selSlot]
  if not it then return false, "No items to place" end
  local b, x, y, z = at(dir)
  local nm = short(it.name)
  if b and b.name == "minecraft:oak_sapling" and nm == "bone_meal" then
    b.bone = (b.bone or 0) + 1
    it.count = it.count - 1
    if it.count == 0 then inv[selSlot] = nil end
    M.boneUsed = (M.boneUsed or 0) + 1
    treeTick()
    return true
  end
  if b and b.drive and it.name == "computercraft:disk" and not b.disk and not M.driveTopOnly then      -- right-clicking the drive with a floppy puts it in
    b.disk = it.name
    it.count = it.count - 1
    if it.count == 0 then inv[selSlot] = nil end
    return true
  end
  if b then return false, "Cannot place block here" end
  if nm:find("sapling", 1, true) then
    local below = W[key(x, y - 1, z)]
    if not (below and (below.name == "minecraft:dirt" or below.name == "minecraft:grass_block")) then return false, "Cannot place block here" end
    W[key(x, y, z)] = { name = it.name, planted = now }
    M.planted = (M.planted or 0) + 1
  elseif nm == "furnace" then
    W[key(x, y, z)] = { name = it.name }
    M.placedFurnaces = (M.placedFurnaces or 0) + 1
  elseif nm == "chest" then
    W[key(x, y, z)] = { name = it.name, inv = {} }
  elseif it.name == "computercraft:turtle_normal" then
    M.nextId = (M.nextId or 100) + 1
    W[key(x, y, z)] = { name = it.name, inv = {}, size = 16, id = M.nextId }
  elseif it.name == "computercraft:disk_drive" then
    W[key(x, y, z)] = { name = it.name, drive = true }
  elseif it.name == "minecraft:hopper" then
    W[key(x, y, z)] = { name = it.name, inv = {}, hopper = true }
  else
    return false, "Cannot place block here"
  end
  it.count = it.count - 1
  if it.count == 0 then inv[selSlot] = nil end
  return true
end
turtle.place = function() return placeDir("f") end
turtle.placeUp = function() return placeDir("u") end
turtle.placeDown = function() return placeDir("d") end

local GRID = { 1, 2, 3, 5, 6, 7, 9, 10, 11 }
turtle.craft = function(limit)
  bump()
  if M.noCraft then return nil end
  -- the grid as a string, row by row
  local pat, n = {}, math.huge
  for i, s in ipairs(GRID) do
    local it = inv[s]
    pat[i] = it and short(it.name) or "-"
    if it then n = math.min(n, it.count) end
  end
  if M.strictCraft then                                      -- like the real pack: anything outside the grid in the inventory blocks the craft
    local inGrid = {}
    for _, s in ipairs(GRID) do inGrid[s] = true end
    for s = 1, 16 do if inv[s] and not inGrid[s] then return false, "No matching recipes" end end
  end
  local want = table.concat(pat, ",")
  for _, r in ipairs(M.RECIPES) do
    if table.concat(r.grid, ",") == want then
      n = math.min(n, limit or 64)
      for _, s in ipairs(GRID) do
        if inv[s] then inv[s].count = inv[s].count - n; if inv[s].count == 0 then inv[s] = nil end end
      end
      local out = r.count * n
      local outName = r.out:find(":", 1, true) and r.out or ("minecraft:" .. r.out)
      local sel = inv[selSlot]
      if sel and sel.name ~= outName then return false, "selected slot not free" end
      addItem(outName, out)
      M.crafted = (M.crafted or 0) + n
      return true
    end
  end
  return false, "No matching recipe"
end

local craftFn = turtle.craft
turtle.craftReal = craftFn
turtle.equipRight = function()
  local it = inv[selSlot]
  if M.plainTurtle and it and it.name == "minecraft:crafting_table" then
    it.count = it.count - 1
    if it.count == 0 then inv[selSlot] = nil end
    if M.workbenchOnly then M.workbenchSide = "right" else turtle.craft = craftFn end
    M.equipped = true
    return true
  end
  return false, "Cannot equip"
end
turtle.equipLeft = turtle.equipRight
function M.makePlain() M.plainTurtle = true; turtle.craft = nil; M.workbenchSide = nil end
function M.makeCrafty() M.plainTurtle = false; turtle.craft = craftFn; M.workbenchSide = nil end

-------------------------------------------------------------- setup API
function M.reset(spec)
  spec = spec or {}
  W, now, actions, ABORT = {}, 0, 0, nil
  T = { x = 0, y = 0, z = 0, f = 0 }
  inv, selSlot, fuel = {}, 1, spec.fuel or 2000
  M.minY = spec.minY or -1000
  M.errors = {}
  for _, k in ipairs({ "logs", "moves", "digs", "planted", "grown", "smelted", "crafted", "lost", "ground", "boneUsed", "burned", "sleeps",
                       "dugProtected", "leaves", "junkIn", "placedFurnaces", "noCraft" }) do M[k] = nil end
  for k in pairs(files) do files[k] = nil end
  M.RECIPES = spec.recipes or {}
  for _, b in ipairs(spec.blocks or {}) do
    local blk = { name = b[4] }
    if b.inv then blk.inv = {}; for _, st in ipairs(b.inv) do blk.inv[#blk.inv + 1] = { name = st[1], count = st[2] } end end
    W[key(b[1], b[2], b[3])] = blk
  end
  for k, v in pairs(spec.fill or {}) do end
  for _, it in ipairs(spec.items or {}) do inv[it[1]] = { name = it[2], count = it[3] } end
  M.noCraft = spec.noCraft
  M.posts, M.replyAfter, M.termPending, M.httpDown, M.replyQueue, M.shellRuns, M.stopAfterRun, M.routeText = {}, nil, false, false, nil, {}, false, nil
  M.storageReplies, M.noPeripheral, M.failMap, M.setupReplies, M.setupHandler, M.booted, M.nextId = nil, nil, nil, nil, nil, nil, nil
  M.makeCrafty(); M.equipped = nil
end
function M.floor(x0, x1, z0, z1, y, name)
  for x = x0, x1 do for z = z0, z1 do W[key(x, y, z)] = { name = name or "minecraft:grass_block" } end end
end
function M.box(x0, x1, y0, y1, z0, z1, name)
  for x = x0, x1 do for y = y0, y1 do for z = z0, z1 do W[key(x, y, z)] = { name = name } end end end
end
function M.removeBlock(x, y, z) W[key(x, y, z)] = nil end
function M.setBlock(x, y, z, name, stacks)
  if name == nil then W[key(x, y, z)] = nil; return end
  local b = { name = name }
  if stacks then b.inv = {}; for _, st in ipairs(stacks) do b.inv[#b.inv + 1] = { name = st[1], count = st[2] } end end
  W[key(x, y, z)] = b
end
function M.block(x, y, z) return W[key(x, y, z)] end
function M.count(pred)
  local n = 0
  for k, b in pairs(W) do if pred(b, k) then n = n + 1 end end
  return n
end
function M.chestCount(x, y, z, name)
  local b = W[key(x, y, z)]
  local n = 0
  if b and b.inv then for _, st in ipairs(b.inv) do if not name or st.name == name then n = n + st.count end end end
  return n
end
function M.invCount(name)
  local n = 0
  for i = 1, 16 do if inv[i] and (not name or inv[i].name == name) then n = n + inv[i].count end end
  return n
end
function M.turtle() return T.x, T.y, T.z, T.f end
function M.abortAfter(n) ABORT = actions + n end
function M.stats() return { fuel = fuel, now = now, actions = actions } end
function M.run(src, ...)
  local f, err = load(src, "=program")
  if not f then error(err) end
  local prog = f(...)
  return prog
end
function M.runMain(src, ...)
  local prog = M.run(src, ...)
  return pcall(prog.main)
end
return M
