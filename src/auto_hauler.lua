-- Carve hauler: carries items between the chests of your other jobs. Each leg says where to take items from
-- (a job's output chest), where to put them (another job's input chest) and which items (part of a name, e.g. "log").
-- It asks the Designer app where those chests are, walks there (climbing over what is in the way, never digging),
-- stands on top of the chest and takes or drops items from there.
-- Needs: live reporting, and the start position of this turtle and of the jobs (Fleet tab, or GPS).
-- Give it some coal or charcoal to start; it also burns charcoal it is carrying when it runs low.
-- Run again with  stop  to cancel the automatic restart.

local args = { ... }

--@@PLAN@@

local STATE_FILE = "carve.hauler"
local TITLE = PLAN.name or "Hauler"
local FUEL_HINT = "coal or charcoal"
local BURN = { "coal", "charcoal" }
local KEEP = {}

--@@COMMON@@

local carried = 0

local function matches(name, pat)
  return name ~= nil and not isBuildItem(name) and (pat == nil or pat == "" or name:find(pat, 1, true) ~= nil)
end

-- ask the app where the chests of every leg are (in my own frame)
local function ask()
  if not fleet.on then return nil, "Live reporting is off" end
  local parts = {}
  for i, l in ipairs(PLAN.legs) do
    parts[i] = '{"from":' .. jq(l.from) .. ',"to":' .. jq(l.to) .. "}"
  end
  local ok, res = pcall(http.post, { url = LIVE_URL .. "/route", timeout = 5, headers = { ["Content-Type"] = "application/json" },
    body = '{"v":1,"id":' .. os.getComputerID() .. ',"legs":[' .. table.concat(parts, ",") .. "]}" })
  if not ok or not res then return nil, "Can't reach the app" end
  local text = ""
  pcall(function() text = res.readAll() or ""; res.close() end)
  local out = {}
  for line in text:gmatch("[^\n]+") do
    local i, a, b, c, d, e, f = line:match("^leg (%d+) (-?%d+) (-?%d+) (-?%d+) (-?%d+) (-?%d+) (-?%d+)$")
    if i then
      out[tonumber(i)] = { from = { tonumber(a), tonumber(b), tonumber(c) }, to = { tonumber(d), tonumber(e), tonumber(f) } }
    else
      local j, why = line:match("^leg (%d+) %? (.*)$")
      if j then out[tonumber(j)] = { err = why } end
    end
  end
  return out
end

-- standing on a chest: take every stack that matches `pat` (other stacks go straight back)
local function takeFrom(pat)
  local held = {}
  for s = 1, 16 do held[s] = itemName(s) end
  for _ = 1, 60 do
    if freeSlots() <= 1 then break end
    if not turtle.suckDown() then break end
  end
  local got = 0
  for s = 1, 16 do
    local n = itemName(s)
    if n and n ~= held[s] and not matches(n, pat) then
      turtle.select(s)
      turtle.dropDown()
    elseif n and matches(n, pat) then
      got = got + turtle.getItemCount(s)
    end
  end
  turtle.select(1)
  return got
end

-- standing on a chest: put in everything that matches `pat`; returns how many items went in
local function giveTo(pat)
  local moved = 0
  for s = 1, 16 do
    local n = itemName(s)
    if matches(n, pat) then
      local c = turtle.getItemCount(s)
      turtle.select(s)
      if turtle.dropDown() then moved = moved + c - turtle.getItemCount(s) end
    end
  end
  turtle.select(1)
  return moved
end

local function cargoCount(pat)
  local c = 0
  for s = 1, 16 do
    if matches(itemName(s), pat) then c = c + turtle.getItemCount(s) end
  end
  return c
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
  else
    fs.delete(STATE_FILE)
    pos.x, pos.y, pos.z, face = 0, 0, 0, 1
    savePos()
  end
  if not fleet.on then
    say(TITLE, "", "Live reporting is off, so I can't", "ask where the chests are.", "Upload me with live reporting", "ticked, and start the Fleet tab.")
    return
  end
  installStartup()
  local rounds = 0
  while true do
    local routes, why = ask()
    local moved = 0
    if not routes then
      say(TITLE, "", why or "No answer from the app", "Waiting...")
    else
      for i, leg in ipairs(PLAN.legs) do
        local r = routes[i]
        local label = tostring(leg.from) .. " -> " .. tostring(leg.to)
        if not r or r.err then
          say(TITLE, "", "Leg " .. i .. ": " .. label, (r and r.err) or "no answer", "Skipping it for now.")
          sleep(2)
        else
          say(TITLE, "", "Leg " .. i .. ": " .. label, "Going to take " .. (leg.item ~= "" and leg.item or "everything"))
          if travelTo(r.from[1], r.from[2], r.from[3]) then
            takeFrom(leg.item)
            if cargoCount(leg.item) > 0 then
              say(TITLE, "", "Leg " .. i .. ": " .. label, "Carrying " .. cargoCount(leg.item) .. " items")
              if travelTo(r.to[1], r.to[2], r.to[3]) then
                local n = giveTo(leg.item)
                moved = moved + n
                carried = carried + n
                fleet.n = carried
              else
                say(TITLE, "", "Leg " .. i .. ": can't reach the", "drop-off chest. Will try again.")
                sleep(3)
              end
            end
          else
            say(TITLE, "", "Leg " .. i .. ": can't reach the", "pick-up chest. Will try again.")
            sleep(3)
          end
        end
      end
    end
    rounds = rounds + 1
    if PLAN.cycles > 0 and rounds >= PLAN.cycles then break end
    if moved == 0 then waitSeconds(PLAN.wait, "Nothing to carry. Waiting.") end
  end
  removeStartup()
  fs.delete(STATE_FILE)
  finish(TITLE, "", "Done. " .. carried .. " items carried.")
end

if rawget(_G, "CARVE_TEST") then
  return { main = main, pos = pos }
end
runMain(main)
