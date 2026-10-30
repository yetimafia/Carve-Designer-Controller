-- Carve agent: an idle turtle that waits for orders. Start a program on it from the Designer's Fleet tab,
-- or from another turtle with   carve start <this turtle's id> <program>.
-- Needs the  carve  menu program installed on this turtle (the install command from the designer's GitHub tab).
-- Run again with  stop  to cancel the automatic restart.
--
-- The Agent: an idle turtle that waits for a job from the Fleet page. The Foreman builds these and gives each a starter kit.
-- The kit arrives in a chest in front of the turtle (collectKit) because turtle.drop into another turtle does not insert in this pack.

local args = { ... }

--@@PLAN@@

local STATE_FILE = "carve.agent"
local TITLE = PLAN.name or "Agent"
local FUEL_HINT = "coal"
local BURN = { "coal", "charcoal" }

--@@COMMON@@

-- a turtle the Foreman built finds its starter kit (coal, saplings, chests...) in a chest next to it, and eats some of the coal
local function collectKit()
  if not fs.exists("carve.kit") then return end
  fs.delete("carve.kit")
  say(TITLE, "", "Looking for my starter kit...")
  for f = 1, 4 do
    turnTo(f)
    local ok, blk = turtle.inspect()
    if ok and type(blk) == "table" and tostring(blk.name):find("chest", 1, true) then
      local guard = 0
      while guard < 40 and turtle.suck() do guard = guard + 1 end
    end
  end
  turnTo(1)
  turtle.select(1)
  burn(1000)
end

local function main()
  if not turtle then printError("This program must run on a turtle."); return end
  if args[1] == "stop" then
    removeStartup(); fs.delete(STATE_FILE)
    finish(TITLE, "", "Stopped. The automatic restart is removed.")
    return
  end
  if not fleet.on then
    say(TITLE, "", "Live reporting is off, so", "nobody can reach me.", "Upload me with live reporting", "ticked, and start the Fleet tab.")
    return
  end
  pos.x, pos.y, pos.z, face = 0, 0, 0, 1
  installStartup()
  collectKit()
  while true do
    say(TITLE, "", "Idle - waiting for a job", "Start me from the Fleet tab, or:", "carve start " .. os.getComputerID() .. " <program>")
    fleetSend(true)
    local cmd, slug = fleet.cmd, fleet.arg
    fleet.cmd, fleet.arg = nil, ""
    local target = fleet.dest
    fleet.dest = nil
    if cmd == "run" and slug ~= "" and slug:match("^[%w_%-]+$") then
      local arrived = true
      if target then
        say(TITLE, "", "Going to the job site for " .. slug, "(" .. target[1] .. ", " .. target[2] .. ", " .. target[3] .. ")")
        fleetSend(true)
        arrived = travelTo(target[1], target[2], target[3])
        if arrived then turnTo(target[4]) end
      end
      local ok = false
      if arrived then
        say(TITLE, "", "Starting " .. slug)
        fleetSend(true)
        ok = shell.run("carve", slug)
      else
        say(TITLE, "", "Could not get to the job site", "for " .. slug .. ". Is the way blocked?")
        fleetSend(true)
        sleep(8)
        ok = true
      end
      if not ok then
        say(TITLE, "", "Could not run " .. slug, "(is the carve menu installed?)")
        fleetSend(true)
        sleep(8)
      end
      pos.x, pos.y, pos.z, face = 0, 0, 0, 1       -- a new place: the agent's own frame starts again
      installStartup()
    else
      sleep(3)
    end
  end
end

if rawget(_G, "CARVE_TEST") then
  return { main = main, pos = pos }
end
runMain(main)
