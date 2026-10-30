#!/usr/bin/env python3
"""
Carve Designer v8.2 - design a dig shape on your PC, put the turtle program on GitHub,
watch the turtle work.

Run:   python carve_designer.py        (Python 3.8+ with tkinter; nothing else to install)

What it does
  * Click/drag cells layer by layer to say what a CC: Tweaked mining turtle should dig.
  * The "Blocks" tab is a picture of the turtle's 16 slots: put torches / blocks in slots, paint
    cells with one as the brush (the turtle digs the cell, then fills it), or add floor torches
    on a grid. The turtle program keeps those slots for placing.
  * Items get a little picture in the colours of the real Minecraft item (our own simplified art, drawn
    by the program; modded items get a coloured square), and you can star favorite items for one-click use. "Browse items..." searches every vanilla item.
  * Dig order: nearest-first (the original), rows (right to left, then forward) or 3-high lanes
    (up, ahead, down at every step). Torches can go in as soon as possible: the turtle tunnels
    to the nearest torch spot first, or places them the moment their cell is dug.
  * "3D view" opens the turtle's whole route as a 3D animation in your web browser (orbit, zoom,
    scrub, speed); "Save 3D page" writes it as one .html file you can send to friends.
  * Textures: "Textures..." (Blocks tab) switches between our built-in simplified pictures and textures
    you import yourself from a resource pack, Minecraft's own version .jar, or a mod .jar (mod items
    get their pictures too). The 3D page has a Textures checkbox; unticked, it shows the rainbow
    layer colours.
  * "Record a video for Discord" saves the 3D replay as a short MP4/WebM (10-60 s, sized to fit Discord).
  * Shapes and templates (cylinder, sphere, dome, pyramid, stairs, mineshaft...), "Import build..." for
    Litematica / WorldEdit / structure files, and "Estimate..." for fuel, time and stacks.
  * Share: Upload can also publish a hosted 3D replay page + gallery; "Open a design from a link...".
  * The turtle can fetch coal from its chest, plug lava/water above and below, and `carve resume`.
  * Turtle skins in the 3D view: green turtle, bee, sea turtle, iron golem, custom colours.
  * Automation tab (v2.0-2.2): ready-made turtle programs that keep running - a tree farm (plants
    saplings, optional bone meal, chops, collects), an auto smelter (feeds furnaces fuel and items,
    empties them; `carve <name> setup` places the furnaces) and an auto crafter (a 3x3 recipe on a
    crafty turtle). Upload them like a design; `carve <name> stop` ends one, `carve resume` continues.
  * Fleet tab (v2.3): every turtle (digs and automation programs) reports its job, fuel, place and
    messages; see them all in the app or on a web page (also on a phone), and press Stop on any of them.
  * Shared world (v2.4-2.6): the Fleet tab places every turtle on one map using GPS or the start position you
    type in; turtles are told where they are and who is nearby. The "Scout" program walks and flies through open
    space (never digging) and maps what it sees; the "Agent" program waits idle until the Fleet tab, or another
    turtle (`carve start <id> <program>`), tells it to start a program.
  * Colony work (v2.7-2.8): the "Miner" program goes underground (shaft, main tunnel, side tunnels), scans every wall
    and mines the ores you choose; "Send job to site..." (Fleet tab) gives a job to the nearest idle agent turtle,
    which walks to the site and starts it - and refuses a job that would overlap one already sent.
  * Colony supply chain (v2.9-3.0): every job places its own chests (give it a chest in the first slot and start it).
    The "Hauler" carries items between the chests of your jobs (tree farm -> smelter that burns logs into charcoal ->
    crafter with the "charcoal blocks" preset). The "Storage keeper" builds a chest warehouse by itself, sorts what
    lands in its drop chest, remembers every item, and the Fleet page's Storage tab lists it and sends items you ask
    for to its pickup chest.
  * "Preview path" replays the turtle's exact route on your shape, layer by layer.
  * "Live view" shows the real turtle moving and mining, as it happens.
  * Every design you make is kept in a list. "Upload" puts it in your GitHub repo next
    to your other designs and keeps a menu program there, so on any turtle you just run
    `carve` and pick one.

Grid axes (top-down view, the turtle faces the TOP of the grid):
  x = right,  z = forward (up on screen),  y = up (layers)
"""
import base64
import collections
import colorsys
import datetime
import gzip
import heapq
import json
import os
import queue
import random
import re
import struct
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import socket
import webbrowser
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

try:
    import tkinter as tk
    from tkinter import filedialog, messagebox, ttk
    TK_OK = True
except Exception:                      # headless / tkinter missing (tests still work)
    TK_OK = False

VERSION = "8.2"     # bump by 0.1 for every idea/feature batch the user adds
GITHUB_API = "https://api.github.com"
MAXDIM = 32          # the turtle saves its progress after every step; keep that file small
DEFAULT_FOLDER = "carve"
DEFAULT_LIVE_URL = "http://127.0.0.1:8765"
CONFIG_DIR = os.path.join(os.path.expanduser("~"), ".carve_designer")
CONFIG_FILE = os.path.join(CONFIG_DIR, "config.json")
LAST_DESIGN_FILE = os.path.join(CONFIG_DIR, "last_design.json")     # old single-design file
ACTION_SECONDS = 0.4                  # one turtle move / dig / turn takes about this long

DIRS = ((1, 0, 0), (-1, 0, 0), (0, 1, 0), (0, -1, 0), (0, 0, 1), (0, 0, -1))

# The turtle-side programs. They are real .lua files in the source tree.
TURTLE_TEMPLATE = r'''-- Carve job: generated by Carve Designer. Runs on a MINING turtle (pickaxe equipped).
--
-- 1. Put the turtle on the "T" cell of your design, facing the way the TOP of the
--    designer's grid points (the designer is a top-down view; up = forward).
-- 2. Optional: a chest directly BEHIND the turtle. It unloads there when full.
-- 3. Put some fuel (coal etc.) in the turtle's inventory.
-- 4. Run this program and press Enter to begin.
-- 5. If the design places blocks / torches: put those items in the slots the start
--    screen lists (the designer's inventory tab shows the same layout).
--
-- Options:  <program> nochest    ignore the chest, wait for you to empty me instead
--           <program> chest      force chest mode on
--           <program> nolive     don't report to the Carve Designer app
-- Ctrl+T stops it. Run the program again to resume where it left off.

-- every turtle names itself after a Deadlock hero (by its id) the first time it starts, if it has no label yet
do
  local GODS = { "Abrams", "Bebop", "Dynamo", "Grey Talon", "Haze", "Infernus", "Ivy", "Kelvin", "Lady Geist", "Lash", "McGinnis", "Krill", "Paradox", "Pocket", "Seven", "Shiv", "Vindicta", "Viscous", "Warden", "Wraith", "Yamato", "Calico", "Holliday", "Vyper", "Sinclair", "Mirage", "Drifter", "Victor", "Paige", "Billy", "Rem", "Mo" }
  if os.getComputerLabel and os.setComputerLabel and os.getComputerID and not os.getComputerLabel() then
    pcall(os.setComputerLabel, GODS[os.getComputerID() % #GODS + 1])
  end
end

local args = { ... }

--@@PLAN@@

---------------------------------------------------------------- settings
-- block names containing any of these words count as a chest to unload into
local CONTAINER_WORDS = { "chest", "barrel", "shulker", "crate", "drawer", "storage" }

local JOB_FILE    = "carve.job"
local MINED_FILE  = "carve.mined"
local POS_FILE    = "carve.pos"
local MARK        = "-- carve autostart"

---------------------------------------------------------------- geometry
-- directions: 1 = +z (forward at start), 2 = +x (right), 3 = -z (back),
--             4 = -x (left), 5 = up, 6 = down
local DX = { 0, 1, 0, -1, 0, 0 }
local DZ = { 1, 0, -1, 0, 0, 0 }
local DY = { 0, 0, 0, 0, 1, -1 }

local job                       -- the plan currently being edited / run
local pos = { x = 1, y = 1, z = 1 }
local face = 1
local stats = { mined = 0, total = 0, placed = 0, ptotal = 0, pfail = 0 }

local function tc(c)
  if term.isColor() then term.setTextColor(c) end
end

local function newJob()
  return { w = 9, d = 9, h = 4, tx = 1, ty = 1, tz = 1, chest = true, name = "Carve job",
           sel = {}, mined = {}, blocked = {},
           inv = {},          -- inv[slot] = item name the turtle keeps in that slot (never dumped)
           place = {},        -- place[cell] = slot to place after the cell is dug out
           placed = {}, pfail = {},
           pattern = "nearest",   -- nearest | rows | lanes
           torches = "first",     -- end | early | first
           seal = false }         -- plug lava/water above and below with spare blocks
end

local function idx(x, y, z) return ((y - 1) * job.d + (z - 1)) * job.w + x end

local function inside(x, y, z)
  return x >= 1 and x <= job.w and y >= 1 and y <= job.h and z >= 1 and z <= job.d
end

---------------------------------------------------------------- files
local function writeFile(name, text)
  local f = fs.open(name, "w")
  if not f then return false end
  f.write(text)
  f.close()
  return true
end

local function readFile(name)
  if not fs.exists(name) then return nil end
  local f = fs.open(name, "r")
  if not f then return nil end
  local t = f.readAll()
  f.close()
  return t
end

local function packSet(set, n)
  local t = {}
  for i = 1, n do t[i] = set[i] and "1" or "0" end
  return table.concat(t)
end

local function unpackSet(str)
  local set = {}
  for i = 1, #str do
    if str:byte(i) == 49 then set[i] = true end
  end
  return set
end

-- slot numbers 1..16 are written as one character: 1-9, a-g (0 = nothing)
local SLOTCHARS = "0123456789abcdefg"

local function packPlace(place, n)
  local t = {}
  for i = 1, n do
    local s = place[i]
    t[i] = s and SLOTCHARS:sub(s + 1, s + 1) or "0"
  end
  return table.concat(t)
end

local function unpackPlace(str)
  local place = {}
  for i = 1, #str do
    local s = tonumber(str:sub(i, i), 17)
    if s and s >= 1 and s <= 16 then place[i] = s end
  end
  return place
end

local function invList()
  local t = {}
  for s = 1, 16 do
    if job.inv[s] then t[#t + 1] = s; t[#t + 1] = job.inv[s] end
  end
  return t
end

local function savePlan(file)
  writeFile(file, textutils.serialise({
    w = job.w, d = job.d, h = job.h, tx = job.tx, ty = job.ty, tz = job.tz,
    chest = job.chest, name = job.name, sel = packSet(job.sel, job.w * job.d * job.h),
    place = packPlace(job.place, job.w * job.d * job.h), inv = invList(),
    pattern = job.pattern, torches = job.torches, seal = job.seal,
  }))
end

local function loadPlan(file)
  local txt = readFile(file)
  if not txt then return nil end
  local t = textutils.unserialise(txt)
  if type(t) ~= "table" or type(t.sel) ~= "string" then return nil end
  local j = newJob()
  j.w, j.d, j.h = t.w or 9, t.d or 9, t.h or 4
  j.tx, j.ty, j.tz = t.tx or 1, t.ty or 1, t.tz or 1
  j.chest = t.chest ~= false
  j.name = type(t.name) == "string" and t.name or "Carve job"
  j.sel = unpackSet(t.sel)
  if type(t.place) == "string" then j.place = unpackPlace(t.place) end
  if t.pattern == "rows" or t.pattern == "lanes" then j.pattern = t.pattern end
  if t.torches == "end" or t.torches == "early" then j.torches = t.torches end
  j.seal = t.seal == true
  if type(t.inv) == "table" then
    for k = 1, #t.inv - 1, 2 do
      if type(t.inv[k]) == "number" and type(t.inv[k + 1]) == "string" then j.inv[t.inv[k]] = t.inv[k + 1] end
    end
  end
  return j
end

local function saveMined()
  local n = job.w * job.d * job.h
  writeFile(MINED_FILE, packSet(job.mined, n) .. "\n" .. packSet(job.blocked, n) .. "\n" .. packSet(job.placed, n))
end

local function savePos()
  writeFile(POS_FILE, pos.x .. "," .. pos.y .. "," .. pos.z .. "," .. face)
end

local function loadProgress()
  local txt = readFile(MINED_FILE)
  if txt then
    local a, b, c = txt:match("^([01]*)\n([01]*)\n?([01]*)")
    job.mined = unpackSet(a or "")
    job.blocked = unpackSet(b or "")
    job.placed = unpackSet(c or "")
  end
  local p = readFile(POS_FILE)
  if p then
    local x, y, z, f = p:match("(%d+),(%d+),(%d+),(%d+)")
    if x then
      pos.x, pos.y, pos.z, face = tonumber(x), tonumber(y), tonumber(z), tonumber(f)
    end
  end
  job.mined[idx(pos.x, pos.y, pos.z)] = true
  job.mined[idx(job.tx, job.ty, job.tz)] = true
end

local function recount()
  local start = idx(job.tx, job.ty, job.tz)
  stats.total, stats.mined, stats.ptotal, stats.placed, stats.pfail = 0, 0, 0, 0, 0
  for i in pairs(job.sel) do
    if i ~= start and not job.blocked[i] then
      stats.total = stats.total + 1
      if job.mined[i] then stats.mined = stats.mined + 1 end
      if job.place[i] then
        stats.ptotal = stats.ptotal + 1
        if job.placed[i] then stats.placed = stats.placed + 1 end
      end
    end
  end
end

local function installStartup()
  if fs.exists("startup.lua") or fs.exists("startup") then return false end
  writeFile("startup.lua", MARK .. "\nshell.run(\"" .. shell.getRunningProgram() .. "\", \"resume\")\n")
  return true
end

local function removeStartup()
  if fs.exists("startup.lua") then
    local t = readFile("startup.lua")
    if t and t:sub(1, #MARK) == MARK then fs.delete("startup.lua") end
  end
end

---------------------------------------------------------------- live view (optional)
-- Streams position and progress to the Carve Designer app so you can watch the
-- turtle work. Fire-and-forget: if the app isn't there, nothing breaks.
local LIVE_URL = PLAN.live or ""
local live = { on = false, why = nil, seq = 0, cells = {}, path = {}, pl = {},
               last = -100, hello = -100, fails = 0, run = os.epoch and math.floor(os.epoch("utc") / 1000) or 0,
               gpsLast = -100, gpsFails = 0, gpsOk = false, gpsDead = false, world = nil }

local function jstr(s)
  s = tostring(s):gsub('[%c"\\]', function(c)
    if c == '"' then return '\\"' end
    if c == "\\" then return "\\\\" end
    return string.format("\\u%04x", c:byte())
  end)
  return '"' .. s .. '"'
end

-- a GPS fix of where the turtle is right now (if a GPS tower and a wireless modem exist); nil otherwise
local function gpsFix(now)
  if live.gpsDead or not (gps and gps.locate) or now - live.gpsLast < 20 then return nil end
  live.gpsLast = now
  local ok, x, y, z = pcall(gps.locate, 1)
  if ok and x then live.gpsOk, live.gpsFails = true, 0; return { x, y, z } end
  live.gpsFails = live.gpsFails + 1
  if live.gpsFails >= 2 and not live.gpsOk then live.gpsDead = true end
end

local function liveSend(msg, flags)
  if not live.on then return end
  live.seq = live.seq + 1
  local now = os.clock()
  local p = {
    '"v":1', '"seq":' .. live.seq, '"id":' .. os.getComputerID(),
    '"name":' .. jstr(job.name or ""),
    '"w":' .. job.w, '"d":' .. job.d, '"h":' .. job.h,
    '"x":' .. pos.x, '"y":' .. pos.y, '"z":' .. pos.z, '"f":' .. face,
    '"mined":' .. stats.mined, '"total":' .. stats.total, '"run":' .. live.run,
    '"rx":' .. (pos.x - job.tx), '"ry":' .. (pos.y - job.ty), '"rz":' .. (pos.z - job.tz),
    '"fuel":' .. jstr(turtle.getFuelLevel()), '"msg":' .. jstr(msg or ""),
    '"pc":' .. stats.placed .. ',"pt":' .. stats.ptotal,
    '"cells":[' .. table.concat(live.cells, ",") .. "]",
    '"pl":[' .. table.concat(live.pl, ",") .. "]",
    '"path":[' .. table.concat(live.path, ",") .. "]",
  }
  if now - live.hello >= 30 then          -- a full picture now and then so the app can join late
    local n = job.w * job.d * job.h
    p[#p + 1] = '"tx":' .. job.tx .. ',"ty":' .. job.ty .. ',"tz":' .. job.tz
    p[#p + 1] = '"chest":' .. (job.chest and "true" or "false")
    p[#p + 1] = '"layers":"' .. packSet(job.sel, n) .. '"'
    p[#p + 1] = '"full":"' .. packSet(job.mined, n) .. '"'
    p[#p + 1] = '"place":"' .. packPlace(job.place, n) .. '"'
    p[#p + 1] = '"placed":"' .. packSet(job.placed, n) .. '"'
    local iv = {}
    for s = 1, 16 do
      if job.inv[s] then iv[#iv + 1] = '"' .. s .. '":' .. jstr(job.inv[s]) end
    end
    p[#p + 1] = '"inv":{' .. table.concat(iv, ",") .. "}"
    live.hello = now
  end
  if flags then p[#p + 1] = flags end
  local fix = gpsFix(now)
  if fix then p[#p + 1] = '"gps":[' .. fix[1] .. "," .. fix[2] .. "," .. fix[3] .. "]" end
  local ok, res = pcall(http.post, {
    url = LIVE_URL .. "/update", body = "{" .. table.concat(p, ",") .. "}", timeout = 5,
    headers = { ["Content-Type"] = "application/json" } })
  if ok and res then
    live.fails = 0
    local reply = ""
    pcall(function() reply = res.readAll() or ""; res.close() end)
    local cmd = reply:match("^ok (%a+)")
    if cmd == "stop" then os.queueEvent("terminate") end                    -- "Stop" pressed on the Fleet page
    live.world = nil
    local wx, wy, wz = reply:match("\nme (-?%d+) (-?%d+) (-?%d+)")
    if wx then live.world = { tonumber(wx), tonumber(wy), tonumber(wz) } end
  else
    live.fails = live.fails + 1
    if live.fails >= 5 then live.on, live.why = false, "can't reach the app" end
  end
  live.cells, live.path, live.pl, live.last = {}, {}, {}, now
end

local function liveTick(msg)
  if live.on and (#live.path >= 60 or os.clock() - live.last >= 1) then liveSend(msg) end
end

local function liveStep()
  if live.on then
    local p = live.path
    p[#p + 1], p[#p + 2], p[#p + 3] = pos.x, pos.y, pos.z
  end
end

local function liveStart()
  if LIVE_URL == "" or live.on then return end
  if not http then live.why = "http is off"; return end
  if http.checkURL then
    local ok, allowed, why = pcall(http.checkURL, LIVE_URL .. "/update")
    if ok and allowed == false then live.why = tostring(why or "blocked"); return end
  end
  live.on, live.hello = true, -100
  local lf = fs.open("carve.live", "w")                -- so "carve start <id> <program>" knows where the app is
  if lf then lf.write(LIVE_URL); lf.close() end
  liveSend("Started")
end

---------------------------------------------------------------- status screen
-- slots the design reserves for items it places (torches, blocks...): never dumped, never burned
local function reserved(s) return job.inv[s] ~= nil end

-- the slot mined items should land in: the first one that isn't reserved
local function workSlot()
  for s = 1, 16 do
    if not reserved(s) then return s end
  end
  return 1
end

local function freeSlots()
  local n = 0
  for s = 1, 16 do
    if not reserved(s) and turtle.getItemCount(s) == 0 then n = n + 1 end
  end
  return n
end

local function status(msg)
  local _, h = term.getSize()
  term.setBackgroundColor(colors.black)
  term.setTextColor(colors.white)
  term.clear()
  term.setCursorPos(1, 1)
  tc(colors.orange)
  print("CARVE - working")
  term.setTextColor(colors.white)
  local pct = stats.total > 0 and math.floor(100 * stats.mined / stats.total) or 100
  print("Mined " .. stats.mined .. " / " .. stats.total .. " (" .. pct .. "%)")
  print("At x" .. pos.x .. " z" .. pos.z .. " layer " .. pos.y)
  if stats.ptotal > 0 then
    print("Placed " .. stats.placed .. " / " .. stats.ptotal)
  end
  print("Fuel " .. tostring(turtle.getFuelLevel()) .. "  free slots " .. freeSlots())
  if live.on then
    print("Live view: on" .. (live.world and ("  at " .. live.world[1] .. " " .. live.world[2] .. " " .. live.world[3]) or ""))
  elseif LIVE_URL ~= "" then
    print("Live view: off (" .. tostring(live.why or "not started") .. ")")
  end
  if msg then
    print("")
    print(msg)
  end
  term.setCursorPos(1, h)
  term.write("Ctrl+T stops (resumable)")
  liveTick(msg)
end

---------------------------------------------------------------- fuel
local function topUp(target)
  local lvl = turtle.getFuelLevel()
  if lvl == "unlimited" then return end
  target = math.min(target, turtle.getFuelLimit())
  for s = 1, 16 do
    if turtle.getFuelLevel() >= target then break end
    if not reserved(s) and turtle.getItemCount(s) > 0 then
      turtle.select(s)
      if turtle.refuel(0) then                -- 0 = just test if it's fuel
        while turtle.getItemCount(s) > 0 and turtle.getFuelLevel() < target do
          if not turtle.refuel(1) then break end
        end
      end
    end
  end
  turtle.select(workSlot())
end

local chestFuel                     -- fetch fuel from the chest at the start (defined further down)
local chestChecked = false             -- looked in the chest already and found no fuel

local function ensureFuel()
  local lvl = turtle.getFuelLevel()
  if lvl == "unlimited" then return end
  -- always keep enough to walk (roughly) back to the start
  local need = math.abs(pos.x - job.tx) + math.abs(pos.y - job.ty) + math.abs(pos.z - job.tz) + 5
  local want = need + ((job.chest and not chestChecked) and 150 or 0)   -- a little spare, to fetch fuel in time
  if lvl >= want then return end
  topUp(need + 200)
  if turtle.getFuelLevel() >= want then return end
  if job.chest and not chestChecked and chestFuel and turtle.getFuelLevel() >= need then
    chestFuel(need)                  -- coal you left in the chest behind the start
  end
  while turtle.getFuelLevel() < need do
    status("Low fuel! Put fuel items in my inventory or in the chest.")
    sleep(3)
    topUp(need + 200)
  end
end

---------------------------------------------------------------- movement
local function turnTo(f)
  local diff = (f - face) % 4
  if diff == 3 then
    turtle.turnLeft()
    face = (face + 2) % 4 + 1
    savePos()
  else
    for _ = 1, diff do                -- remember the heading after every quarter turn
      turtle.turnRight()
      face = face % 4 + 1
      savePos()
    end
  end
end

-- returns detect, dig, inspect, attack, move, place for absolute direction d (turning if needed)
local function act(d)
  if d == 5 then
    return turtle.detectUp, turtle.digUp, turtle.inspectUp, turtle.attackUp, turtle.up, turtle.placeUp
  elseif d == 6 then
    return turtle.detectDown, turtle.digDown, turtle.inspectDown, turtle.attackDown, turtle.down, turtle.placeDown
  end
  turnTo(d)
  return turtle.detect, turtle.dig, turtle.inspect, turtle.attack, turtle.forward, turtle.place
end

---------------------------------------------------------------- sealing lava / water
-- cheap solid blocks the turtle can use to plug a leak (what it dug up on the way)
local SEAL_ITEMS = { cobblestone = true, cobbled_deepslate = true, dirt = true, netherrack = true, stone = true,
                     deepslate = true, andesite = true, diorite = true, granite = true, tuff = true,
                     blackstone = true }

local function sealSlot()
  for s = 1, 16 do
    if not reserved(s) and turtle.getItemCount(s) > 0 then
      local it = turtle.getItemDetail(s)
      if it and it.name then
        local short = it.name:gsub("^[%w_]+:", "")
        if SEAL_ITEMS[short] then return s end
      end
    end
  end
  return nil
end

local function isLiquidName(data)
  local n = type(data) == "table" and data.name or ""
  return n:find("water", 1, true) ~= nil or n:find("lava", 1, true) ~= nil
end

-- with "seal" on: if there is lava or water straight above or below me (outside the part to be dug),
-- plug it with a spare block so it can't flow into the finished room
local function sealVertical()
  if not job.seal then return end
  for _, d in ipairs({ 5, 6 }) do
    local nx, ny, nz = pos.x + DX[d], pos.y + DY[d], pos.z + DZ[d]
    if not (inside(nx, ny, nz) and job.sel[idx(nx, ny, nz)]) then
      local _, _, inspect, _, _, place = act(d)
      local ok, data = inspect()
      if ok and isLiquidName(data) then
        local s = sealSlot()
        if s then
          turtle.select(s)
          if place() then stats.sealed = (stats.sealed or 0) + 1 end
          turtle.select(workSlot())
        end
      end
    end
  end
end

-- move one cell in direction d (the cell must already be dug out)
local function stepTo(d)
  ensureFuel()
  local detect, dig, _, attack, move = act(d)
  local tries = 0
  while true do
    local ok, err = move()
    if ok then
      pos.x, pos.y, pos.z = pos.x + DX[d], pos.y + DY[d], pos.z + DZ[d]
      savePos()
      liveStep()
      liveTick()
      sealVertical()
      return
    end
    tries = tries + 1
    if err and tostring(err):lower():find("fuel") then
      status("Out of fuel! Add fuel to my inventory.")
      sleep(3)
      topUp(500)
    elseif detect() then
      dig()                       -- e.g. gravel that fell into the tunnel
    else
      attack()                    -- a mob is in the way
      sleep(0.4)
    end
    if tries % 20 == 0 then
      status("Something is blocking my path...")
      sleep(2)
    end
  end
end

---------------------------------------------------------------- path finding
-- Breadth-first search through already-dug cells. Returns a list of directions
-- to the nearest cell where goal(x, y, z) is true ({} if already there), or nil.
local function bfs(sx, sy, sz, goal)
  local s = idx(sx, sy, sz)
  local par, pdir = { [s] = false }, {}
  local qx, qy, qz, head, tail = { sx }, { sy }, { sz }, 1, 1
  local order = { face, face % 4 + 1, (face + 1) % 4 + 1, (face + 2) % 4 + 1, 5, 6 }
  while head <= tail do
    local x, y, z = qx[head], qy[head], qz[head]
    head = head + 1
    if goal(x, y, z) then
      local rev, cur = {}, idx(x, y, z)
      while par[cur] do
        rev[#rev + 1] = pdir[cur]
        cur = par[cur]
      end
      local path = {}
      for i = #rev, 1, -1 do path[#path + 1] = rev[i] end
      return path
    end
    local here = idx(x, y, z)
    for _, d in ipairs(order) do
      local nx, ny, nz = x + DX[d], y + DY[d], z + DZ[d]
      if inside(nx, ny, nz) then
        local n = idx(nx, ny, nz)
        if par[n] == nil and job.mined[n] and not job.placed[n] then
          par[n], pdir[n] = here, d
          tail = tail + 1
          qx[tail], qy[tail], qz[tail] = nx, ny, nz
        end
      end
    end
  end
  return nil
end

local function hasWork(x, y, z)
  for d = 1, 6 do
    local nx, ny, nz = x + DX[d], y + DY[d], z + DZ[d]
    if inside(nx, ny, nz) then
      local n = idx(nx, ny, nz)
      if job.sel[n] and not job.mined[n] and not job.blocked[n] then return true end
    end
  end
  return false
end

local function goTo(x, y, z)
  local path = bfs(pos.x, pos.y, pos.z, function(a, b, c) return a == x and b == y and c == z end)
  if not path then error("carve: no path to " .. x .. "," .. y .. "," .. z, 0) end
  for _, d in ipairs(path) do stepTo(d) end
end

---------------------------------------------------------------- digging
local function isLiquid(data)
  local n = type(data) == "table" and data.name or ""
  return n:find("water", 1, true) ~= nil or n:find("lava", 1, true) ~= nil
end

local function isContainer(data)
  if type(data) ~= "table" or not data.name then return false end
  local n = data.name:lower()
  for _, w in ipairs(CONTAINER_WORDS) do
    if n:find(w, 1, true) then return true end
  end
  return false
end

-- dig whatever is in direction d until the cell is free; false if it can't be cleared
local function clearDir(d)
  local detect, dig, inspect = act(d)
  local digs = 0
  for _ = 1, 30 do
    if not detect() then
      if d == 5 and digs > 0 then      -- gravel/sand above may still be falling
        sleep(0.3)
        if not detect() then return true end
      else
        return true
      end
    else
      local dug, derr = dig()
      if dug then
        digs = digs + 1
      else
        if derr and tostring(derr):lower():find("no tool", 1, true) then
          error("I have no digging tool. Equip a pickaxe, then run me again.", 0)
        end
        local ok, data = inspect()
        if ok and isLiquid(data) then return true end
        sleep(0.5)
      end
    end
  end
  return false
end

---------------------------------------------------------------- unloading
local function dumpAtHome()
  topUp(math.huge)                    -- burn spare fuel items first
  turnTo(3)                           -- face the chest behind the start
  while true do
    local ok, data = turtle.inspect()
    if job.chest and ok and isContainer(data) then
      for s = 1, 16 do
        if turtle.getItemCount(s) > 0 then
          local keep = false
          if reserved(s) then                   -- keep the right item, get rid of junk that landed here
            local it = turtle.getItemDetail(s)
            keep = it ~= nil and it.name == job.inv[s]
          end
          if not keep then
            turtle.select(s)
            turtle.drop()
          end
        end
      end
      turtle.select(workSlot())
    end
    if freeSlots() >= 6 then break end
    if job.chest then
      status("Need an empty chest directly behind my start spot. Waiting...")
    else
      status("Inventory full - please empty me. Waiting...")
    end
    sleep(3)
  end
  turnTo(1)
end

local function dumpTrip()
  local bx, by, bz = pos.x, pos.y, pos.z
  goTo(job.tx, job.ty, job.tz)
  dumpAtHome()
  goTo(bx, by, bz)
end

-- out of fuel: go back to the start and burn what is in the chest behind it
chestFuel = function(need)
  chestChecked = true
  local bx, by, bz, bf = pos.x, pos.y, pos.z, face
  status("Low on fuel - fetching coal from the chest...")
  goTo(job.tx, job.ty, job.tz)
  turnTo(3)
  local ok, data = turtle.inspect()
  if ok and isContainer(data) then
    for _ = 1, math.max(1, freeSlots() - 2) do
      if not turtle.suck() then break end
    end
  end
  dumpAtHome()                       -- burns the fuel it took, puts everything else back
  goTo(bx, by, bz)
  turnTo(bf)
end

---------------------------------------------------------------- cells, ranks, torches
local function cellOf(i)
  local i0 = i - 1
  return i0 % job.w + 1, math.floor(i0 / (job.w * job.d)) + 1, math.floor(i0 / job.w) % job.d + 1
end

-- order cells outward from v0: v0, v0+1 ... max, then v0-1 ... 1
local function outward(v, v0, max)
  if v >= v0 then return v - v0 end
  return max - v
end

-- Position of a cell in the chosen dig pattern (smaller = dug earlier). Always unique per cell.
--  rows : one layer at a time; rows go forward; right-to-left, then left-to-right, ...
--  lanes: bands of 3 layers centred on the start layer; each lane runs forward / back
--         along z digging up, down and ahead at every step
local function rankOf(x, y, z)
  if job.pattern == "lanes" then
    local rel = y - job.ty
    local b = math.floor((rel + 1) / 3)
    local up = math.floor((job.h - job.ty + 1) / 3)
    local br = b >= 0 and b or (up - b)
    local mid = job.ty + 3 * b
    local v = (y == mid) and 0 or ((y == mid + 1) and 1 or 2)
    local xl = job.w - x
    local zr = (xl % 2 == 0) and (z - 1) or (job.d - z)
    return ((br * job.w + xl) * job.d + zr) * 3 + v
  end
  local lr = outward(y, job.ty, job.h)
  local ri = outward(z, job.tz, job.d)
  local xr = (ri % 2 == 0) and (job.w - x) or (x - 1)
  return (lr * job.d + ri) * job.w + xr
end

-- The unmined cells next to dug-out cells (the places a pattern can continue from), kept in a
-- binary heap ordered by their position in the pattern, so the next one is always cheap to find.
local heapR, heapC, heapN, inHeap, dropped = {}, {}, 0, {}, {}

local function heapPush(r, c)
  heapN = heapN + 1
  local i = heapN
  while i > 1 do
    local p = math.floor(i / 2)
    if heapR[p] <= r then break end
    heapR[i], heapC[i] = heapR[p], heapC[p]
    i = p
  end
  heapR[i], heapC[i] = r, c
end

local function heapPop()
  local topC = heapC[1]
  local lastR, lastC = heapR[heapN], heapC[heapN]
  heapR[heapN], heapC[heapN] = nil, nil
  heapN = heapN - 1
  if heapN > 0 then
    local i = 1
    while true do
      local l = i * 2
      if l > heapN then break end
      if l < heapN and heapR[l + 1] < heapR[l] then l = l + 1 end
      if heapR[l] >= lastR then break end
      heapR[i], heapC[i] = heapR[l], heapC[l]
      i = l
    end
    heapR[i], heapC[i] = lastR, lastC
  end
  return topC
end

local function frontierAdd(n)               -- n has just been dug
  local x, y, z = cellOf(n)
  for d = 1, 6 do
    local nx, ny, nz = x + DX[d], y + DY[d], z + DZ[d]
    if inside(nx, ny, nz) then
      local m = idx(nx, ny, nz)
      if job.sel[m] and not job.mined[m] and not job.blocked[m] and not inHeap[m] then
        inHeap[m], dropped[m] = true, nil
        heapPush(rankOf(nx, ny, nz), m)
      end
    end
  end
end

local function frontierBuild()
  heapR, heapC, heapN, inHeap, dropped = {}, {}, 0, {}, {}
  for i, v in pairs(job.mined) do
    if v then frontierAdd(i) end
  end
end

-- the unmined cell that comes first in the pattern and that the turtle can stand next to
local function minFrontier()
  while heapN > 0 do
    local n = heapC[1]
    local ok = not (job.mined[n] or job.blocked[n] or dropped[n]) and job.sel[n]
    if ok then
      ok = false
      local x, y, z = cellOf(n)
      for d = 1, 6 do
        local nx, ny, nz = x + DX[d], y + DY[d], z + DZ[d]
        if inside(nx, ny, nz) then
          local m = idx(nx, ny, nz)
          if job.mined[m] and not job.placed[m] then ok = true; break end
        end
      end
    end
    if ok then return n end
    heapPop()                           -- not usable now; it is pushed again if a neighbour gets dug
    inHeap[n] = nil
  end
  return nil
end

---------------------------------------------------------------- placing blocks / torches
local function isTorchSlot(slot)
  local name = job.inv[slot]
  return name ~= nil and name:find("torch", 1, true) ~= nil
end

local function distances()                  -- walking distance from the start over cells that are still open
  local start = idx(job.tx, job.ty, job.tz)
  local dist = { [start] = 0 }
  local qx, qy, qz, head, tail = { job.tx }, { job.ty }, { job.tz }, 1, 1
  while head <= tail do
    local x, y, z = qx[head], qy[head], qz[head]
    head = head + 1
    local dh = dist[idx(x, y, z)]
    for d = 1, 6 do
      local nx, ny, nz = x + DX[d], y + DY[d], z + DZ[d]
      if inside(nx, ny, nz) then
        local n = idx(nx, ny, nz)
        if dist[n] == nil and job.mined[n] and not job.placed[n] then
          dist[n] = dh + 1
          tail = tail + 1
          qx[tail], qy[tail], qz[tail] = nx, ny, nz
        end
      end
    end
  end
  return dist
end

-- which slot holds the item reserved for `slot` (it, or another slot reserved for the same item)
local function supplySlot(slot)
  local want = job.inv[slot]
  local function has(s)
    local it = turtle.getItemDetail(s)
    return it ~= nil and it.name == want
  end
  if has(slot) then return slot end
  for s = 1, 16 do
    if s ~= slot and job.inv[s] == want and has(s) then return s end
  end
  return nil
end

local function markPlaced(n)
  job.placed[n] = true
  stats.placed = stats.placed + 1
  if live.on then live.pl[#live.pl + 1] = n end
  saveMined()
end

-- place the item reserved for `slot` into the (empty) cell in direction d.
-- true = placed, false = it would not go in, nil = no item on board (only with nowait)
local function placeInto(d, slot, nowait)
  local _, _, _, _, _, place = act(d)
  if not clearDir(d) then return false end
  local s = supplySlot(slot)
  if not s and nowait then return nil end
  while not s do
    local left = 0
    for c, sl in pairs(job.place) do
      if sl == slot and not job.placed[c] then left = left + 1 end
    end
    status("Out of " .. tostring(job.inv[slot]) .. ". Put " .. left .. " more in slot " .. slot .. " - I wait.")
    sleep(3)
    s = supplySlot(slot)
  end
  turtle.select(s)
  local ok = false
  for _ = 1, 3 do
    ok = place()
    if ok then break end
    sleep(0.3)
  end
  turtle.select(workSlot())
  return ok
end

-- would every cell still to be dug stay connected to the start if n turned into a block?
local function canBlock(n)
  local start = idx(job.tx, job.ty, job.tz)
  local want = 0
  for i in pairs(job.sel) do
    if not job.placed[i] and not job.blocked[i] and i ~= n then want = want + 1 end
  end
  local seen = { [start] = true }
  local qx, qy, qz, head, tail, count = { job.tx }, { job.ty }, { job.tz }, 1, 1, 1
  while head <= tail do
    local x, y, z = qx[head], qy[head], qz[head]
    head = head + 1
    for d = 1, 6 do
      local nx, ny, nz = x + DX[d], y + DY[d], z + DZ[d]
      if inside(nx, ny, nz) then
        local m = idx(nx, ny, nz)
        if not seen[m] and m ~= n and job.sel[m] and not job.placed[m] and not job.blocked[m] then
          seen[m] = true
          count = count + 1
          tail = tail + 1
          qx[tail], qy[tail], qz[tail] = nx, ny, nz
        end
      end
    end
  end
  if count ~= want then return false end
  -- ...and the turtle must still be able to walk to every cell it has already dug out
  local open = 0
  for i in pairs(job.mined) do
    if not job.placed[i] and i ~= n then open = open + 1 end
  end
  seen = { [start] = true }
  qx, qy, qz, head, tail, count = { job.tx }, { job.ty }, { job.tz }, 1, 1, 1
  while head <= tail do
    local x, y, z = qx[head], qy[head], qz[head]
    head = head + 1
    for d = 1, 6 do
      local nx, ny, nz = x + DX[d], y + DY[d], z + DZ[d]
      if inside(nx, ny, nz) then
        local m = idx(nx, ny, nz)
        if not seen[m] and m ~= n and job.mined[m] and not job.placed[m] then
          seen[m] = true
          count = count + 1
          tail = tail + 1
          qx[tail], qy[tail], qz[tail] = nx, ny, nz
        end
      end
    end
  end
  return count == open
end

-- Torches are dropped straight down onto the floor from the cell above (placeDown), so they
-- stand on a block that stays put instead of hanging on the side of one the turtle will break.
local digCell
local torchCells = {}                 -- every torch cell of the job, in cell order
local pdefer = {}                     -- torches that would have cut off work: they wait for the end
local dry = {}                        -- torch slots found empty during the dig

local function buildTorchList()
  torchCells = {}
  for n, slot in pairs(job.place) do
    if isTorchSlot(slot) then torchCells[#torchCells + 1] = n end
  end
  table.sort(torchCells)
  pdefer, dry = {}, {}
end

local function torchSpot(n)           -- the cell the turtle stands in to drop torch n down
  local x, y, z = cellOf(n)
  if inside(x, y + 1, z) then return idx(x, y + 1, z) end
  return nil
end

-- is there (or will there be, once its block is in) something solid under torch cell n?
local function supportReady(n)
  local x, y, z = cellOf(n)
  if not inside(x, y - 1, z) then return true end
  local b = idx(x, y - 1, z)
  if not job.sel[b] or job.blocked[b] then return true end
  local s = job.place[b]
  if s and not isTorchSlot(s) then return job.placed[b] == true end
  return false
end

local function supplyOk(slot)
  if dry[slot] then return false end
  if supplySlot(slot) then return true end
  dry[slot] = true
  return false
end

-- could torch n go in during the dig? (its cell is dug or will be dug, its floor is solid, one is on board)
local function torchReady(n)
  local slot = job.place[n]
  return not job.placed[n] and not job.pfail[n] and not pdefer[n] and not job.blocked[n]
    and job.sel[n] ~= nil and supportReady(n) and supplyOk(slot)
end

-- stand above torch cell n, dig it out if it is still stone, and drop the torch in
local function putTorch(n)
  local a = torchSpot(n)
  local ax, ay, az = cellOf(a)
  goTo(ax, ay, az)
  if job.sel[n] and not job.mined[n] and not job.blocked[n] then digCell(n, 6) end
  if not job.mined[n] then return end
  if not canBlock(n) then
    pdefer[n] = true
    return
  end
  if placeInto(6, job.place[n]) then
    markPlaced(n)
  else
    job.pfail[n] = true
    stats.pfail = stats.pfail + 1
  end
end

---------------------------------------------------------------- digging routines
-- dig the cell n lying in direction d from where the turtle stands
digCell = function(n, d)
  if freeSlots() < 2 then dumpTrip() end
  if clearDir(d) then
    job.mined[n] = true
    stats.mined = stats.mined + 1
    if live.on then live.cells[#live.cells + 1] = n end
    frontierAdd(n)
    if job.seal and (d == 5 or d == 6) then
      -- a ceiling / floor cell: step in and look past it, so lava or water behind it can be plugged
      local bx, by, bz = pos.x + 2 * DX[d], pos.y + 2 * DY[d], pos.z + 2 * DZ[d]
      if not (inside(bx, by, bz) and job.sel[idx(bx, by, bz)]) then
        stepTo(d)
        stepTo(d == 5 and 6 or 5)
      end
    end
    return true
  end
  job.blocked[n] = true
  stats.total = stats.total - 1
  return false
end

local function wanted(n)
  return job.sel[n] and not job.mined[n] and not job.blocked[n]
end

-- dig every selected neighbour of the current cell (without moving)
local function digNeighbors()
  local list = { 5, 6 }
  for k = 0, 3 do list[#list + 1] = (face - 1 + k) % 4 + 1 end
  for _, d in ipairs(list) do
    local nx, ny, nz = pos.x + DX[d], pos.y + DY[d], pos.z + DZ[d]
    if inside(nx, ny, nz) then
      local n = idx(nx, ny, nz)
      if wanted(n) then digCell(n, d) end
    end
  end
end

-- dig what is directly above and below the turtle
local function digVertical()
  for _, d in ipairs({ 5, 6 }) do
    local nx, ny, nz = pos.x + DX[d], pos.y + DY[d], pos.z + DZ[d]
    if inside(nx, ny, nz) then
      local n = idx(nx, ny, nz)
      if wanted(n) then digCell(n, d) end
    end
  end
end

-- walk next to cell t and dig it. true = dug, false = it can't be broken, nil = no way to reach it
local function digTarget(t)
  local tx, ty, tz = cellOf(t)
  local path = bfs(pos.x, pos.y, pos.z, function(x, y, z)
    for d = 1, 6 do
      if x + DX[d] == tx and y + DY[d] == ty and z + DZ[d] == tz then return true end
    end
    return false
  end)
  if not path then return nil end
  for _, d in ipairs(path) do stepTo(d) end
  for d = 1, 6 do
    if pos.x + DX[d] == tx and pos.y + DY[d] == ty and pos.z + DZ[d] == tz then
      return digCell(t, d)
    end
  end
  return nil
end

-- "torches first": tunnel to the cell above the nearest torch spot, put the torch in, repeat
local mission = nil

local function findMission()
  local spotOf, any = {}, false
  for _, n in ipairs(torchCells) do
    if torchReady(n) then
      local a = torchSpot(n)
      if a and (job.mined[a] or wanted(a)) and not job.placed[a] then
        spotOf[a] = n
        any = true
      end
    end
  end
  if not any then return nil end
  local total = job.w * job.d * job.h
  local par, queue, head, tail = {}, {}, 1, 0
  for i = 1, total do
    if job.mined[i] and not job.placed[i] then
      par[i] = false
      tail = tail + 1
      queue[tail] = i
      if spotOf[i] then return { path = {}, n = spotOf[i] } end
    end
  end
  while head <= tail do
    local c = queue[head]
    head = head + 1
    local x, y, z = cellOf(c)
    for d = 1, 6 do
      local nx, ny, nz = x + DX[d], y + DY[d], z + DZ[d]
      if inside(nx, ny, nz) then
        local n = idx(nx, ny, nz)
        if par[n] == nil and wanted(n) then
          par[n] = c
          if spotOf[n] then
            local rev, cur = {}, n
            while par[cur] do
              rev[#rev + 1] = cur
              cur = par[cur]
            end
            local path = {}
            for k = #rev, 1, -1 do path[#path + 1] = rev[k] end
            return { path = path, n = spotOf[n] }
          end
          tail = tail + 1
          queue[tail] = n
        end
      end
    end
  end
  return nil
end

local function missionStep()
  if job.torches ~= "first" or #torchCells == 0 then return false end
  if mission then
    while #mission.path > 0 and not wanted(mission.path[1]) do table.remove(mission.path, 1) end
    if not torchReady(mission.n) then mission = nil end
  end
  if not mission then mission = findMission() end
  if not mission then return false end
  if #mission.path > 0 then
    if digTarget(mission.path[1]) == nil then
      mission = nil
      return false
    end
  else
    local n = mission.n
    mission = nil
    local a = torchSpot(n)
    if job.mined[a] and not job.placed[a] then
      putTorch(n)
    else                                    -- the standing cell turned out to be unbreakable
      job.pfail[n] = true
      stats.pfail = stats.pfail + 1
    end
  end
  saveMined()
  status("Mining...")
  return true
end

-- "as soon as their cell is dug": a torch whose cell and standing cell are both open goes in now
local function readyStep()
  if job.torches ~= "early" or #torchCells == 0 then return false end
  local spots, any = {}, false
  for _, n in ipairs(torchCells) do
    if job.mined[n] and not job.placed[n] and not job.pfail[n] and not pdefer[n] and supportReady(n) then
      local a = torchSpot(n)
      if a and job.mined[a] and not job.placed[a] and supplyOk(job.place[n]) then
        spots[a] = n
        any = true
      end
    end
  end
  if not any then return false end
  local path = bfs(pos.x, pos.y, pos.z, function(x, y, z) return spots[idx(x, y, z)] ~= nil end)
  if not path then return false end
  for _, d in ipairs(path) do stepTo(d) end
  putTorch(spots[idx(pos.x, pos.y, pos.z)])
  saveMined()
  status("Placing torches...")
  return true
end

local function nearestStep()
  digNeighbors()
  saveMined()
  status("Mining...")
  local path = bfs(pos.x, pos.y, pos.z, hasWork)
  if not path or #path == 0 then return false end
  for _, d in ipairs(path) do stepTo(d) end
  return true
end

local function orderedStep()
  if job.pattern == "lanes" then digVertical() end
  local t = minFrontier()
  if not t then return false end
  if digTarget(t) == nil then dropped[t] = true end
  saveMined()
  status("Mining...")
  return true
end

local function digAll()
  frontierBuild()
  buildTorchList()
  mission = nil
  local ordered = job.pattern ~= "nearest"
  while true do
    if not missionStep() and not readyStep() then
      if ordered then
        if not orderedStep() then break end
      else
        if not nearestStep() then break end
      end
    end
  end
  if ordered then                       -- sweep up anything the pattern left behind
    while nearestStep() do end
  end
end

-- Runs after everything is dug (and also picks up torches that could not go in earlier).
-- Cells are done farthest-first (by walking distance from the start), so the turtle never
-- seals itself in: whatever it needs to walk over to get home is nearer than the cell it fills.
local function placePhase()
  if next(job.place) == nil then return end
  if #torchCells == 0 then buildTorchList() end
  local start = idx(job.tx, job.ty, job.tz)
  local dist = distances()
  local list = {}
  for n in pairs(job.place) do
    if job.mined[n] and n ~= start and dist[n] and not job.placed[n] and job.inv[job.place[n]]
       and not isTorchSlot(job.place[n]) then
      list[#list + 1] = n
    end
  end
  table.sort(list, function(a, b)
    if dist[a] ~= dist[b] then return dist[a] > dist[b] end
    return a < b
  end)
  for _, n in ipairs(list) do
    if not job.pfail[n] then
      local x, y, z = cellOf(n)
      local sx, sy, sz, dir
      for d = 1, 6 do                       -- stand on a cell one step nearer to the start
        local ax, ay, az = x - DX[d], y - DY[d], z - DZ[d]
        if inside(ax, ay, az) and dist[idx(ax, ay, az)] == dist[n] - 1 then
          sx, sy, sz, dir = ax, ay, az, d
          break
        end
      end
      if sx then
        goTo(sx, sy, sz)
        if placeInto(dir, job.place[n]) then
          markPlaced(n)
        else
          job.pfail[n] = true
          stats.pfail = stats.pfail + 1
        end
        status("Placing...")
      end
    end
  end
end

-- Last of all: torches that could not go in earlier (their floor block had to be placed first).
local function torchPhase()
  if #torchCells == 0 then return end
  local dist = distances()
  local list = {}
  for _, n in ipairs(torchCells) do
    local a = torchSpot(n)
    if a and job.mined[n] and not job.placed[n] and not job.pfail[n] and supportReady(n) and dist[a] then
      list[#list + 1] = n
    end
  end
  table.sort(list, function(p, q)
    local dp, dq = dist[torchSpot(p)], dist[torchSpot(q)]
    if dp ~= dq then return dp > dq end
    return p < q
  end)
  for _, n in ipairs(list) do
    local ax, ay, az = cellOf(torchSpot(n))
    local path = bfs(pos.x, pos.y, pos.z, function(x, y, z) return x == ax and y == ay and z == az end)
    if path then
      for _, d in ipairs(path) do stepTo(d) end
      if placeInto(6, job.place[n]) then
        markPlaced(n)
      else
        job.pfail[n] = true
        stats.pfail = stats.pfail + 1
      end
      status("Placing torches...")
    end
  end
end

---------------------------------------------------------------- the job
local function finish()
  liveSend("Finished", '"done":true')
  fs.delete(JOB_FILE)
  fs.delete(MINED_FILE)
  fs.delete(POS_FILE)
  removeStartup()
  local left = 0
  for i in pairs(job.sel) do
    if not job.mined[i] then left = left + 1 end
  end
  term.setBackgroundColor(colors.black)
  term.setTextColor(colors.white)
  term.clear()
  term.setCursorPos(1, 1)
  tc(colors.lime)
  print("Carve complete!")
  term.setTextColor(colors.white)
  print("Mined " .. stats.mined .. " blocks.")
  if left > 0 then print(left .. " cells could not be broken or reached.") end
  if stats.ptotal > 0 then
    print("Placed " .. stats.placed .. " of " .. stats.ptotal .. " blocks.")
    if stats.pfail > 0 then print(stats.pfail .. " could not be placed (nothing to hold them?).") end
  end
end

local function runJob()
  turtle.select(workSlot())
  liveStart()
  digAll()
  placePhase()
  torchPhase()
  local home = bfs(pos.x, pos.y, pos.z, function(x, y, z) return x == job.tx and y == job.ty and z == job.tz end)
  if home then
    for _, d in ipairs(home) do stepTo(d) end
    if job.chest then dumpAtHome() end
    turnTo(1)
  end
  finish()
end

local function runGuarded()
  local ok, err = pcall(runJob)
  if ok then return end
  removeStartup()
  pcall(liveSend, tostring(err):find("Terminated") and "Stopped" or ("Error: " .. tostring(err)),
        '"stopped":true')
  term.setBackgroundColor(colors.black)
  term.setTextColor(colors.white)
  term.clear()
  term.setCursorPos(1, 1)
  if tostring(err):find("Terminated") then
    print("Stopped. Run the program again to resume.")
  else
    printError("Error: " .. tostring(err))
    print("Run the program again to try resuming.")
  end
end

local function resumeJob()
  local j = loadPlan(JOB_FILE)
  if not j then return false end
  job = j
  loadProgress()
  recount()
  runGuarded()
  return true
end

local function startRun(run)
  job = run
  pos.x, pos.y, pos.z, face = job.tx, job.ty, job.tz, 1
  savePlan(JOB_FILE)
  saveMined()
  savePos()
  installStartup()
  recount()
  runGuarded()
end

---------------------------------------------------------------- planning
-- flood fill over selected cells starting at the turtle's cell
local function floodReach(sel)
  local reach = {}
  local sx, sy, sz = job.tx, job.ty, job.tz
  reach[idx(sx, sy, sz)] = true
  local qx, qy, qz, head, tail = { sx }, { sy }, { sz }, 1, 1
  while head <= tail do
    local x, y, z = qx[head], qy[head], qz[head]
    head = head + 1
    for d = 1, 6 do
      local nx, ny, nz = x + DX[d], y + DY[d], z + DZ[d]
      if inside(nx, ny, nz) then
        local n = idx(nx, ny, nz)
        if sel[n] and not reach[n] then
          reach[n] = true
          tail = tail + 1
          qx[tail], qy[tail], qz[tail] = nx, ny, nz
        end
      end
    end
  end
  return reach
end

-- copy the design into a runnable job: protect the chest, drop unreachable cells
local function buildRun()
  local run = { w = job.w, d = job.d, h = job.h, tx = job.tx, ty = job.ty, tz = job.tz,
                chest = job.chest, name = job.name, sel = {}, mined = {}, blocked = {},
                inv = {}, place = {}, placed = {}, pfail = {},
                pattern = job.pattern, torches = job.torches, seal = job.seal }
  local start = idx(job.tx, job.ty, job.tz)
  for i in pairs(job.sel) do run.sel[i] = true end
  run.sel[start] = true
  if job.chest and job.tz > 1 then
    run.sel[idx(job.tx, job.ty, job.tz - 1)] = nil      -- never dig out the chest
  end
  local reach = floodReach(run.sel)
  for s, name in pairs(job.inv) do run.inv[s] = name end
  local total, skipped = 0, 0
  for i in pairs(run.sel) do
    if reach[i] then
      if i ~= start then
        total = total + 1
        if job.place[i] and job.inv[job.place[i]] then run.place[i] = job.place[i] end
      end
    else
      run.sel[i] = nil
      skipped = skipped + 1
    end
  end
  run.mined[start] = true
  return run, total, skipped
end

---------------------------------------------------------------- text UI
local function clearScreen()
  term.setBackgroundColor(colors.black)
  term.setTextColor(colors.white)
  term.clear()
  term.setCursorPos(1, 1)
end

local function waitKey()
  while true do
    local ev, k = os.pullEvent()
    if ev == "key" then return k end
  end
end

local function countdown(secs)
  for i = secs, 1, -1 do
    clearScreen()
    print("Resuming carve job in " .. i .. "s")
    print("Press any key to cancel.")
    local t = os.startTimer(1)
    while true do
      local ev, a = os.pullEvent()
      if ev == "key" then return false end
      if ev == "timer" and a == t then break end
    end
  end
  return true
end

local function resumeMenu()
  clearScreen()
  tc(colors.orange)
  print("Unfinished carve job found")
  term.setTextColor(colors.white)
  print("It was stopped part-way.")
  print("Check I'm still where I stopped.")
  print("")
  print("Enter = resume")
  print("D     = discard that job")
  while true do
    local k = waitKey()
    if k == keys.enter then return "resume" end
    if k == keys.d then return "discard" end
  end
end

local function planJob()
  local j = newJob()
  j.w, j.d, j.h = PLAN.w, PLAN.d, PLAN.h
  j.tx, j.ty, j.tz = PLAN.tx, PLAN.ty, PLAN.tz
  j.chest = PLAN.chest
  j.name = PLAN.name or "Carve job"
  j.sel = unpackSet(table.concat(PLAN.layers))
  for s, name in pairs(PLAN.inv or {}) do j.inv[s] = name end
  if PLAN.place then j.place = unpackPlace(table.concat(PLAN.place)) end
  if PLAN.pattern == "rows" or PLAN.pattern == "lanes" then j.pattern = PLAN.pattern end
  if PLAN.torches == "end" or PLAN.torches == "early" then j.torches = PLAN.torches end
  j.seal = PLAN.seal == true
  return j
end

---------------------------------------------------------------- main
local function main()
  if not turtle then
    printError("This program must run on a turtle.")
    return
  end

  local chestOverride
  for _, a in ipairs(args) do
    if a == "nochest" then chestOverride = false end
    if a == "chest" then chestOverride = true end
    if a == "nolive" then LIVE_URL = "" end
  end

  -- automatic resume after the world reloads (see startup.lua)
  if args[1] == "resume" and fs.exists(JOB_FILE) then
    if countdown(5) and resumeJob() then return end
  end

  if fs.exists(JOB_FILE) and fs.exists(POS_FILE) then
    if resumeMenu() == "resume" then
      if resumeJob() then return end
    end
    fs.delete(JOB_FILE)
    fs.delete(MINED_FILE)
    fs.delete(POS_FILE)
    removeStartup()
  end

  job = planJob()
  if chestOverride ~= nil then job.chest = chestOverride end
  local run, total, skipped = buildRun()

  clearScreen()
  local _, sh = term.getSize()
  local used = 0
  local function line(text)
    print(text)
    used = used + 1
  end
  tc(colors.orange)
  line(PLAN.name or "Carve job")
  term.setTextColor(colors.white)
  line("Shape " .. PLAN.w .. "x" .. PLAN.d .. "x" .. PLAN.h .. "  to mine: " .. total)
  if skipped > 0 then line("Unreachable, skipped: " .. skipped) end
  line("Fuel: " .. tostring(turtle.getFuelLevel()) .. "  Chest behind: " .. (job.chest and "YES" or "NO"))
  line("Stand on the START cell, facing the")
  line("top edge of the design.")
  if LIVE_URL ~= "" then line("Live view: " .. LIVE_URL) end
  if next(run.inv) then
    local need = {}
    for _, sl in pairs(run.place) do need[sl] = (need[sl] or 0) + 1 end
    local rows = {}
    for sl = 1, 16 do
      if run.inv[sl] then
        local it = turtle.getItemDetail(sl)
        local have = (it and it.name == run.inv[sl]) and it.count or 0
        local want = need[sl] or 0
        rows[#rows + 1] = { text = sl .. ": " .. run.inv[sl]:gsub("^minecraft:", "") .. "  " .. want .. "/" .. have,
                            short = have < want }
      end
    end
    local room = sh - used - 2                 -- keep a row for the header and one for the prompt
    if #rows > room then room = room - 1 end
    for i = 1, math.min(#rows, room) do
      if i == 1 then line("Slot: item  need/have") end
      if rows[i].short then tc(colors.red) end
      line(rows[i].text)
      term.setTextColor(colors.white)
    end
    if #rows > room then line("...and " .. (#rows - room) .. " more") end
  end
  if total == 0 then
    print("Nothing to mine.")
    return
  end
  print("Enter = begin, other key = cancel")
  if waitKey() ~= keys.enter then
    clearScreen()
    print("Cancelled.")
    return
  end
  startRun(run)
end

if rawget(_G, "CARVE_TEST") then
  return {
    main = main, startRun = startRun, resumeJob = resumeJob, buildRun = buildRun,
    getJob = function() return job end, setJob = function(j) job = j end,
    newJob = newJob, idx = idx, loadPlan = loadPlan, planJob = planJob,
  }
end

main()
'''
LAUNCHER_TEMPLATE = r'''-- carve : menu of your Carve Designer programs, stored on GitHub.
--
--   carve                  pick a program from the list
--   carve <name>           download and run one directly   (name = its short name)
--   carve <name> nochest   anything after the name is passed to the program
--   carve list             just show the list
--   carve resume           carry on with the job that was interrupted
--   carve ping [address]  check that this turtle can reach the Designer app (for live reporting)
--   carve start <id> <name>   tell another turtle (running the "agent" program) to start a program
--
-- Every run downloads the newest version, so after you upload a changed design
-- from the designer you don't need to do anything else on the turtle.

-- every turtle names itself after a Deadlock hero (by its id) the first time it starts, if it has no label yet
do
  local GODS = { "Abrams", "Bebop", "Dynamo", "Grey Talon", "Haze", "Infernus", "Ivy", "Kelvin", "Lady Geist", "Lash", "McGinnis", "Krill", "Paradox", "Pocket", "Seven", "Shiv", "Vindicta", "Viscous", "Warden", "Wraith", "Yamato", "Calico", "Holliday", "Vyper", "Sinclair", "Mirage", "Drifter", "Victor", "Paige", "Billy", "Rem", "Mo" }
  if os.getComputerLabel and os.setComputerLabel and os.getComputerID and not os.getComputerLabel() then
    pcall(os.setComputerLabel, GODS[os.getComputerID() % #GODS + 1])
  end
end

local BASE = @@BASE@@
local args = { ... }

if not http then
  error("HTTP is turned off on this computer/server, so I can't reach GitHub.", 0)
end

if args[1] == "ping" then
  local url = args[2]
  if not url then
    local f = fs.open("carve.live", "r")
    url = f and f.readAll() or nil
    if f then f.close() end
  end
  if not url or url == "" then
    print("Use:  carve ping http://<address of the Designer>:8765")
    return
  end
  url = url:gsub("/+$", "")
  print("Trying " .. url .. " ...")
  local h, err = http.get(url .. "/")
  if h then
    h.close()
    print("OK: the Designer answered. Programs on this turtle can report to it.")
    return
  end
  err = tostring(err)
  print("Failed: " .. err)
  local low = err:lower()
  if low:find("not permitted", 1, true) or low:find("blocked", 1, true) or low:find("denied", 1, true) then
    print("Minecraft blocks that address. In computercraft-server.toml set the")
    print("\"$private\" http rule to allow (or add the address), then restart the world/server.")
  elseif low:find("refused", 1, true) or low:find("connect", 1, true) or low:find("timed out", 1, true) or low:find("timeout", 1, true) then
    print("Nothing answered. Is 'Start listening' on in the Designer? Is the address the PC's")
    print("network address (not 127.0.0.1) if this turtle is on a server or another computer?")
    print("Tick 'Accept turtles from other computers' and allow the firewall prompt.")
  else
    print("Check the address: http://<PC address>:8765")
  end
  return
end

if args[1] == "start" then
  local id, slug = tonumber(args[2]), args[3]
  if not id or not slug or not slug:match("^[%w_%-]+$") then
    print("Use:  carve start <turtle id> <program>")
    return
  end
  local f = fs.open("carve.live", "r")
  local url = f and f.readAll() or ""
  if f then f.close() end
  if url == "" then
    error("I don't know where the Designer app is yet. Run any program with live reporting on this turtle once.", 0)
  end
  local h, err = http.post(url .. "/cmd", textutils.serialiseJSON({ id = id, cmd = "run", arg = slug }))
  if h then
    h.close()
    print("Asked turtle " .. id .. " to start " .. slug .. ".")
  else
    print("Not accepted (" .. tostring(err) .. "). Is turtle " .. id .. " running the agent program?")
  end
  return
end

local function fetch(path)
  -- the extra number defeats GitHub's short-lived cache so you always get the latest
  local stamp = tostring(os.epoch and os.epoch("utc") or os.time())
  local h, err = http.get(BASE .. "/" .. path .. "?nocache=" .. stamp)
  if not h then return nil, tostring(err) end
  local body = h.readAll()
  h.close()
  return body
end

local function loadList()
  local body, err = fetch("index.json")
  if not body then
    return nil, "Could not download the list (" .. err .. "). Is the repo public and the address right?"
  end
  local ok, data = pcall(textutils.unserialiseJSON, body)
  if not ok or type(data) ~= "table" or type(data.programs) ~= "table" then
    return nil, "The list on GitHub isn't readable. Upload a design from the designer again."
  end
  return data.programs
end

local function valid(p)
  return type(p) == "table" and type(p.slug) == "string" and p.slug:match("^[%w_%-]+$")
    and type(p.file) == "string" and not p.file:find("..", 1, true) and not p.file:find("^/")
end

local function describe(p)
  local size = ""
  if type(p.size) == "table" then size = (" %dx%dx%d"):format(p.size[1] or 0, p.size[2] or 0, p.size[3] or 0) end
  local blocks = p.blocks and (" - " .. tostring(p.blocks) .. " blocks") or ""
  return tostring(p.name or p.slug) .. size .. blocks
end

local function run(p, extra)
  local body, err = fetch(p.file)
  if not body then error("Could not download " .. p.slug .. ": " .. err, 0) end
  local localName = "job_" .. p.slug
  local f = fs.open(localName, "w")
  if not f then error("Could not save " .. localName, 0) end
  f.write(body)
  f.close()
  print("Downloaded " .. localName .. " (" .. #body .. " bytes)")
  local lf = fs.open("carve.last", "w")
  if lf then lf.write(p.slug); lf.close() end
  shell.run(localName, table.unpack(extra))
end

local programs, err = loadList()
if not programs then error(err, 0) end
local list = {}
for _, p in ipairs(programs) do
  if valid(p) then list[#list + 1] = p end
end
if #list == 0 then error("No programs on GitHub yet. Upload one from the designer.", 0) end

local function find(slug)
  for _, p in ipairs(list) do
    if p.slug == slug then return p end
  end
end

if args[1] == "list" then
  for i, p in ipairs(list) do print(i .. ") " .. p.slug .. "  " .. describe(p)) end
  return
end

local function lastSlug()
  if not (fs.exists("carve.job") and fs.exists("carve.last")) then return nil end
  local f = fs.open("carve.last", "r")
  if not f then return nil end
  local slug = f.readAll()
  f.close()
  return slug
end

if args[1] == "resume" then
  local slug = lastSlug()
  local p = slug and find(slug)
  if not p then
    print("Nothing to resume here.")
    return
  end
  run(p, { "resume" })
  return
end

if args[1] and args[1] ~= "" then
  local p = find(args[1])
  if not p then error("No program called '" .. args[1] .. "'. Try: carve list", 0) end
  run(p, { table.unpack(args, 2) })
  return
end

local _, termH = term.getSize()
local perPage = math.max(3, termH - 5)
local page = 1
local pages = math.ceil(#list / perPage)
while true do
  term.clear()
  term.setCursorPos(1, 1)
  print("Carve programs (" .. page .. "/" .. pages .. ")")
  for i = (page - 1) * perPage + 1, math.min(#list, page * perPage) do
    print(i .. ") " .. describe(list[i]))
  end
  print("")
  local pending = lastSlug()
  if pending and find(pending) then print("r = resume the unfinished " .. pending .. " job") end
  write("Number" .. (pages > 1 and ", n/p = page" or "") .. ", q = quit: ")
  local answer = read()
  local n = tonumber(answer)
  if answer == "q" or answer == "Q" then
    return
  elseif (answer == "r" or answer == "R") and pending and find(pending) then
    term.clear()
    term.setCursorPos(1, 1)
    run(find(pending), { "resume" })
    return
  elseif answer == "n" and page < pages then
    page = page + 1
  elseif answer == "p" and page > 1 then
    page = page - 1
  elseif n and list[n] then
    term.clear()
    term.setCursorPos(1, 1)
    run(list[n], {})
    return
  end
end
'''
# The design model: a grid of cells (what to dig / place), the turtle's 16 item slots and the file format that is saved
# and uploaded. Everything else (simulator, GUI, GitHub) works on these objects.
# Why it is first: the other parts are glued together in the order build.py lists them, and they all need the model.
# ======================================================================= model
def slugify(name):
    """Short, file-safe name used for the program's file name in the repo."""
    s = re.sub(r"[^a-z0-9]+", "_", (name or "").lower()).strip("_")
    return s[:30].strip("_") or "design"


def clean_name(name):
    name = re.sub(r"[^A-Za-z0-9 _.,:()\-]", "", name or "").strip()
    return name[:30] or "Carve job"


# Items the turtle can carry for placing. (name, colour shown in the designer)
ITEM_PRESETS = [
    ("minecraft:torch", "#fff35c"), ("minecraft:lantern", "#ffb347"), ("minecraft:glowstone", "#ffd54a"),
    ("minecraft:sea_lantern", "#bdf7ee"), ("minecraft:cobblestone", "#9aa0a6"), ("minecraft:stone", "#7d8590"),
    ("minecraft:stone_bricks", "#6b7280"), ("minecraft:smooth_stone", "#aeb4bb"),
    ("minecraft:cobbled_deepslate", "#4b5058"), ("minecraft:deepslate_bricks", "#3d4046"),
    ("minecraft:bricks", "#c0504d"), ("minecraft:sandstone", "#e8d9a0"), ("minecraft:oak_planks", "#c8a165"),
    ("minecraft:spruce_planks", "#7a5a37"), ("minecraft:dirt", "#8b5a2b"), ("minecraft:glass", "#a5f3fc"),
    ("minecraft:iron_bars", "#c8ccd0"), ("minecraft:ladder", "#b08850"), ("minecraft:chest", "#d9822b"),
]
PATTERNS = [("nearest", "Nearest first (the original way)"),
            ("rows", "Rows: right to left, then forward"),
            ("lanes", "3-high lanes: up, ahead, down")]
TORCH_MODES = [("first", "Torches first (tunnel to them)"),
               ("early", "As soon as their cell is dug"),
               ("end", "After everything is dug")]
DEFAULT_FAVORITES = ["minecraft:torch", "minecraft:cobblestone", "minecraft:stone_bricks", "minecraft:glass"]
MAX_SUPPLY_SLOTS = 8        # the turtle needs the other slots for what it digs up
SLOT_CHARS = "0123456789abcdefg"       # slot 1-16 as one character (0 = none), same as the turtle program
TORCH = "minecraft:torch"


def clean_item(name):
    """'torch' / 'Minecraft:Torch' -> 'minecraft:torch'; None when it isn't a usable item id."""
    name = (name or "").strip().lower().replace(" ", "_")
    if not name:
        return None
    if ":" not in name:
        name = "minecraft:" + name
    if len(name) > 60 or ".." in name or not re.fullmatch(r"[a-z0-9_.\-]+:[a-z0-9_/.\-]+", name):
        return None
    return name


def item_label(name):
    return name.split(":", 1)[-1].replace("_", " ")


def item_color(name):
    st = icon_stats(name)                      # vanilla items: the colour measured from the game
    if st is not None:
        return "#%02x%02x%02x" % st[1]
    for n, col in ITEM_PRESETS:
        if n == name:
            return col
    h = sum((i + 1) * ord(ch) for i, ch in enumerate(name)) % 360       # stable colour for modded items
    r, g, b = colorsys.hsv_to_rgb(h / 360.0, 0.45, 0.95)
    return "#%02x%02x%02x" % (int(r * 255), int(g * 255), int(b * 255))


SKINS = [("crafty", "Crafty turtle"), ("classic", "Green turtle"), ("bee", "Bee"), ("sea", "Sea turtle"),
         ("golem", "Iron golem"), ("custom", "Custom colours")]
SKIN_COLORS = {"crafty": "#aab0ba", "classic": "#7ddc4a", "bee": "#f5c518", "sea": "#3a9d5a", "golem": "#c9c9c4"}


MARK_FACES = ("forward", "right", "back", "left")


class Design:
    """Cells are (x, y, z), 1-based. x = right, y = up (layer), z = forward.

    sel   - cells to dig out
    inv   - turtle slot (1-16) -> item the turtle keeps in that slot for placing
    place - cell -> slot: after this cell is dug out, put that slot's item into it
    """
    def __init__(self, w=9, d=9, h=4):
        self.w, self.d, self.h = w, d, h
        self.tx, self.ty, self.tz = 1, 1, 1      # where the turtle stands
        self.chest = True
        self.sel = set()
        self.inv = {}
        self.place = {}
        self.pattern = "nearest"        # which order the cells are dug in
        self.torch_mode = "first"       # when torches go in
        self.seal = False               # plug lava / water above and below with spare blocks
        self.skin = "crafty"            # how the turtle looks in the previews
        self.skin_body, self.skin_accent = "#6fe36f", "#1c7c3c"     # colours of the "custom" skin
        self.name = "Carve job"
        self.marks = {}                 # base design: station name -> (x, y, z, face), face = forward / right / back / left of the design

    def copy(self):
        c = Design(self.w, self.d, self.h)
        c.tx, c.ty, c.tz, c.chest, c.name = self.tx, self.ty, self.tz, self.chest, self.name
        c.sel = set(self.sel)
        c.marks = dict(self.marks)
        c.inv = dict(self.inv)
        c.place = dict(self.place)
        c.pattern, c.torch_mode, c.seal = self.pattern, self.torch_mode, self.seal
        c.skin, c.skin_body, c.skin_accent = self.skin, self.skin_body, self.skin_accent
        return c

    def inside(self, x, y, z):
        return 1 <= x <= self.w and 1 <= y <= self.h and 1 <= z <= self.d

    @property
    def turtle(self):
        return (self.tx, self.ty, self.tz)

    @property
    def chest_cell(self):
        """The cell directly behind the turtle (only inside the grid if tz > 1)."""
        return (self.tx, self.ty, self.tz - 1) if self.tz > 1 else None

    def slug(self):
        return slugify(self.name)

    def set_cell(self, x, y, z, on, slot=None):
        """Select / unselect a cell. `slot` (with on=True) also says what to place there afterwards;
        on=True without a slot means "just dig it" and forgets any block assigned before."""
        c = (x, y, z)
        if c == self.turtle or not self.inside(x, y, z):
            return
        if on:
            self.sel.add(c)
            if slot is not None and slot in self.inv:
                self.place[c] = slot
            else:
                self.place.pop(c, None)
        else:
            self.sel.discard(c)
            self.place.pop(c, None)

    def cell_state(self, c):
        """(dug?, slot to place or None) - what a brush stroke compares with."""
        return (c in self.sel, self.place.get(c))

    def set_slot_item(self, slot, name):
        """Assign an item to a turtle slot (name=None frees the slot and forgets its blocks)."""
        if name is None:
            self.inv.pop(slot, None)
            for c in [c for c, s in self.place.items() if s == slot]:
                del self.place[c]
            return True
        if not 1 <= slot <= 16 or (slot not in self.inv and len(self.inv) >= MAX_SUPPLY_SLOTS):
            return False
        self.inv[slot] = name
        return True

    def resize(self, w, d, h):
        self.sel = {c for c in self.sel if c[0] <= w and c[1] <= h and c[2] <= d}
        self.place = {c: s for c, s in self.place.items() if c in self.sel}
        self.w, self.d, self.h = w, d, h
        self.tx, self.tz, self.ty = min(self.tx, w), min(self.tz, d), min(self.ty, h)
        self.sel.discard(self.turtle)
        self.place.pop(self.turtle, None)
        self.marks = {n: m for n, m in self.marks.items() if m[0] <= w and m[1] <= h and m[2] <= d}

    def set_mark(self, name, x, y, z, face="forward"):
        """Mark a cell of the base design as the start cell of a turtle job (name = the job's name)."""
        if not self.inside(x, y, z):
            raise ValueError("That cell is outside the grid.")
        if face not in MARK_FACES:
            raise ValueError("Facing must be forward, right, back or left.")
        name = clean_name(name)
        for n in [n for n, m in self.marks.items() if m[:3] == (x, y, z)]:
            del self.marks[n]                                # one station per cell
        self.marks[name] = (x, y, z, face)

    # ---- (de)serialisation: one 0/1 string per layer, z-major then x (matches the Lua side)
    def layer_strings(self):
        out = []
        for y in range(1, self.h + 1):
            out.append("".join("1" if (x, y, z) in self.sel else "0"
                               for z in range(1, self.d + 1) for x in range(1, self.w + 1)))
        return out

    def place_strings(self, cells=None):
        cells = self.place if cells is None else cells
        out = []
        for y in range(1, self.h + 1):
            out.append("".join(SLOT_CHARS[cells.get((x, y, z), 0)]
                               for z in range(1, self.d + 1) for x in range(1, self.w + 1)))
        return out

    def to_json(self):
        data = {"app": "carve-designer", "version": 1, "name": self.name,
                "w": self.w, "d": self.d, "h": self.h,
                "tx": self.tx, "ty": self.ty, "tz": self.tz,
                "chest": self.chest, "layers": self.layer_strings()}
        if self.inv:
            data["inv"] = {str(s): n for s, n in sorted(self.inv.items())}
        if self.place:
            data["place"] = self.place_strings()
        if self.pattern != "nearest":
            data["pattern"] = self.pattern
        if self.torch_mode != "first":
            data["torches"] = self.torch_mode
        if self.seal:
            data["seal"] = True
        if self.marks:
            data["marks"] = {n: list(m) for n, m in sorted(self.marks.items())}
        if self.skin != "crafty":
            data["skin"] = self.skin
        if self.skin == "custom":
            data["skinColors"] = [self.skin_body, self.skin_accent]
        return data

    @staticmethod
    def from_json(data):
        w, d, h = int(data["w"]), int(data["d"]), int(data["h"])
        if not (1 <= w <= MAXDIM and 1 <= d <= MAXDIM and 1 <= h <= MAXDIM):
            raise ValueError("size out of range")
        des = Design(w, d, h)
        des.tx, des.ty, des.tz = int(data["tx"]), int(data["ty"]), int(data["tz"])
        if not des.inside(*des.turtle):
            raise ValueError("turtle position outside the grid")
        des.chest = bool(data.get("chest", True))
        des.name = clean_name(str(data.get("name", "Carve job")))
        layers = data["layers"]
        if len(layers) != h:
            raise ValueError("layer count does not match height")
        for y, row in enumerate(layers, 1):
            if len(row) != w * d or set(row) - set("01"):
                raise ValueError("bad layer data")
            for i, ch in enumerate(row):
                if ch == "1":
                    des.sel.add((i % w + 1, y, i // w + 1))
        des.sel.discard(des.turtle)
        _read_inv(des, data.get("inv"))
        _read_place(des, data.get("place"))
        if data.get("pattern", "nearest") not in dict(PATTERNS) or data.get("torches", "first") not in dict(TORCH_MODES):
            raise ValueError("unknown pattern")
        des.pattern = data.get("pattern", "nearest")
        des.seal = data.get("seal") is True
        if data.get("skin") in dict(SKINS):
            des.skin = data["skin"]
        cols = data.get("skinColors")
        if (isinstance(cols, list) and len(cols) == 2
                and all(isinstance(c, str) and re.fullmatch(r"#[0-9a-fA-F]{6}", c) for c in cols)):
            des.skin_body, des.skin_accent = cols[0].lower(), cols[1].lower()
        des.torch_mode = data.get("torches", "first")
        marks = data.get("marks") or {}
        if not isinstance(marks, dict) or len(marks) > 40:
            raise ValueError("bad station marks")
        for n, m in marks.items():
            if not (isinstance(m, list) and len(m) == 4 and all(isinstance(v, int) and not isinstance(v, bool) for v in m[:3])
                    and m[3] in MARK_FACES):
                raise ValueError("bad station mark")
            des.set_mark(n, m[0], m[1], m[2], m[3])
        return des


def _read_inv(des, inv):
    if inv is None:
        return
    if not isinstance(inv, dict) or len(inv) > MAX_SUPPLY_SLOTS:
        raise ValueError("bad inventory data")
    for k, v in inv.items():
        slot, name = int(k), clean_item(str(v))
        if not 1 <= slot <= 16 or name is None:
            raise ValueError("bad inventory data")
        des.inv[slot] = name


def _read_place(des, layers):
    """layers: one string per layer (as place_strings) or None."""
    if not layers:
        return
    if len(layers) != des.h:
        raise ValueError("block layer count does not match height")
    for y, row in enumerate(layers, 1):
        if len(row) != des.w * des.d or set(row) - set(SLOT_CHARS):
            raise ValueError("bad block data")
        for i, ch in enumerate(row):
            slot = SLOT_CHARS.index(ch)
            c = (i % des.w + 1, y, i // des.w + 1)
            if slot and slot in des.inv and c in des.sel:
                des.place[c] = slot


def design_from_flat(name, w, d, h, turtle, chest, flat, place="", inv=None):
    """Rebuild a design from the turtle's own report (all layers joined into one 0/1 string)."""
    w, d, h = int(w), int(d), int(h)
    if not (1 <= w <= MAXDIM and 1 <= d <= MAXDIM and 1 <= h <= MAXDIM) or len(flat) != w * d * h:
        raise ValueError("bad design from turtle")
    des = Design(w, d, h)
    des.name, des.chest = clean_name(str(name)), bool(chest)
    des.tx, des.ty, des.tz = (int(v) for v in turtle)
    if not des.inside(*des.turtle):
        raise ValueError("turtle position outside the grid")
    for i, ch in enumerate(flat):
        if ch == "1":
            des.sel.add((i % w + 1, i // (w * d) + 1, (i % (w * d)) // w + 1))
    des.sel.discard(des.turtle)
    _read_inv(des, inv)
    if place:
        if len(place) != w * d * h or set(place) - set(SLOT_CHARS):
            raise ValueError("bad block data from turtle")
        _read_place(des, [place[y * w * d:(y + 1) * w * d] for y in range(h)])
    return des


def cell_from_index(i, w, d):
    """The turtle's 1-based cell index (as used in its Lua code) -> (x, y, z)."""
    i0 = i - 1
    return (i0 % w + 1, i0 // (w * d) + 1, (i0 % (w * d)) // w + 1)


def flood(sel, start):
    """Cells of `sel` reachable from `start` by face-adjacent steps (start included)."""
    seen = {start}
    stack = [start]
    while stack:
        x, y, z = stack.pop()
        for dx, dy, dz in DIRS:
            n = (x + dx, y + dy, z + dz)
            if n not in seen and n in sel:
                seen.add(n)
                stack.append(n)
    return seen


def build_run(design):
    """Mirror of the turtle's planner: returns (cells_to_mine_incl_start, total, skipped)."""
    start = design.turtle
    run = set(design.sel)
    run.add(start)
    cc = design.chest_cell
    if design.chest and cc is not None:
        run.discard(cc)                       # never dig out the chest
    reach = flood(run, start)
    skipped = len(run - reach)
    return reach, len(reach) - 1, skipped


def _is_torch(design, slot):
    return "torch" in design.inv.get(slot, "")


def _torch_valid(design, run, raw, c):
    """A torch is dropped straight down from the cell above it onto the floor, so it needs a dug cell
    above (to stand in, with nothing placed there) and something solid below that stays."""
    a = (c[0], c[1] + 1, c[2])
    if a not in run or a in design.place:
        return False
    b = (c[0], c[1] - 1, c[2])
    if design.chest and b == design.chest_cell:
        return False
    if b not in run:
        return True                               # the ground, or a block that is left alone
    s = raw.get(b)
    return s is not None and not any(wd in design.inv.get(s, "") for wd in NONSOLID_WORDS)


def _raw_place(design):
    run, _total, _skipped = build_run(design)
    start = design.turtle
    return run, {c: s for c, s in design.place.items() if c in run and c != start and s in design.inv}


def build_place(design):
    """What the turtle will really place: {cell: slot} for reachable cells (never the start or chest).
    Torches that have no dug cell above them or no solid floor under them are left out."""
    run, raw = _raw_place(design)
    return {c: s for c, s in raw.items() if not _is_torch(design, s) or _torch_valid(design, run, raw, c)}


def bad_torches(design):
    """Torch cells that can't be placed (nothing to stand in above them / no solid floor)."""
    run, raw = _raw_place(design)
    return sorted(c for c, s in raw.items() if _is_torch(design, s) and not _torch_valid(design, run, raw, c))


def supply_needs(design):
    """{slot: number of blocks the job places from it}"""
    need = {}
    for s in build_place(design).values():
        need[s] = need.get(s, 0) + 1
    return need


NONSOLID_WORDS = ("torch", "lantern", "ladder", "pane", "bars", "chain", "rod", "door", "sign")


def auto_torches(design, spacing, slot):
    """Mark floor cells on a grid for torches. Returns how many were added.

    A torch goes on the floor of the finished room - an open (dug, nothing placed) cell with
    something solid under it and a dug cell above it for the turtle to stand in - every `spacing`
    cells, centred in each square. If you fill the floor with blocks, torches sit on top of them.
    Cells that already have a block are left alone.
    """
    spacing = max(1, int(spacing))
    run, _total, _skipped = build_run(design)
    start = design.turtle

    def solid_below(c):
        b = (c[0], c[1] - 1, c[2])
        if b in design.place:
            item = design.inv.get(design.place[b], "")
            return not any(w in item for w in NONSOLID_WORDS)
        return b not in run

    added = 0
    for c in sorted(run):
        above = (c[0], c[1] + 1, c[2])
        if c == start or c in design.place or not solid_below(c) or above not in run or above in design.place:
            continue
        if (c[0] - 1) % spacing == spacing // 2 and (c[2] - 1) % spacing == spacing // 2:
            design.place[c] = slot
            added += 1
    return added


def clear_blocks(design, slot=None):
    """Forget placement for every cell (or only those using `slot`); the digging stays."""
    for c in [c for c, s in design.place.items() if slot is None or s == slot]:
        del design.place[c]


# ================================================================ generated programs
def normalize_live_url(url):
    """http://host:port  ->  cleaned, or '' when it isn't something the turtle can use."""
    url = (url or "").strip().rstrip("/")
    if re.fullmatch(r"http://[A-Za-z0-9._\-]+(:\d{1,5})?", url):
        return url
    return ""


def generate_lua(design, live_url=""):
    live_url = normalize_live_url(live_url)
    plan = [
        "-- Shape: %dx%dx%d (right x forward x up), turtle cell x=%d y=%d z=%d" % (
            design.w, design.d, design.h, design.tx, design.ty, design.tz),
        "local PLAN = {",
        '  name = "%s",' % clean_name(design.name),
        '  live = "%s",' % live_url,
        "  w = %d, d = %d, h = %d," % (design.w, design.d, design.h),
        "  tx = %d, ty = %d, tz = %d," % (design.tx, design.ty, design.tz),
        "  chest = %s," % ("true" if design.chest else "false"),
        '  pattern = "%s", torches = "%s",' % (design.pattern, design.torch_mode),
        '  seal = %s,' % ("true" if design.seal else "false"),
        "  layers = {",
    ]
    for y, row in enumerate(design.layer_strings(), 1):
        plan.append('    "%s",  -- layer %d' % (row, y))
    plan.append("  },")
    if design.inv:
        plan.append("  inv = { %s }," % ", ".join('[%d] = "%s"' % (s, n) for s, n in sorted(design.inv.items())))
    valid = build_place(design)
    if valid:
        plan.append("  place = {")
        for y, row in enumerate(design.place_strings(valid), 1):
            plan.append('    "%s",  -- layer %d' % (row, y))
        plan.append("  },")
    plan.append("}")
    return TURTLE_TEMPLATE.replace("--@@PLAN@@", "\n".join(plan), 1)


def check_repo_settings(repo, branch, folder):
    """Validate/clean the GitHub settings. Returns (repo, branch, folder)."""
    repo = (repo or "").strip().strip("/")
    if not re.fullmatch(r"[A-Za-z0-9_.\-]+/[A-Za-z0-9_.\-]+", repo):
        raise UploadError("Repository must look like  owner/name")
    branch = (branch or "").strip() or "main"
    if not re.fullmatch(r"[A-Za-z0-9_.\-/]+", branch) or ".." in branch:
        raise UploadError("That branch name has characters I can't use.")
    folder = (folder or "").strip().strip("/")
    if folder and (not re.fullmatch(r"[A-Za-z0-9_.\-/]+", folder) or ".." in folder):
        raise UploadError("Folder may only use letters, digits, _ - . and /")
    return repo, branch, folder


def repo_path(folder, rel):
    return (folder + "/" + rel) if folder else rel


def raw_base(repo, branch, folder):
    base = "https://raw.githubusercontent.com/%s/%s" % (repo, urllib.parse.quote(branch, safe="/"))
    return base + ("/" + urllib.parse.quote(folder, safe="/") if folder else "")


def generate_launcher(repo, branch, folder):
    repo, branch, folder = check_repo_settings(repo, branch, folder)
    return LAUNCHER_TEMPLATE.replace("@@BASE@@", json.dumps(raw_base(repo, branch, folder)), 1)


# ============================================================= saved designs & settings
def library_dir():
    return os.path.join(CONFIG_DIR, "designs")


def library_save(design):
    os.makedirs(library_dir(), exist_ok=True)
    slug = design.slug()
    tmp = os.path.join(library_dir(), slug + ".json.tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(design.to_json(), f)
    os.replace(tmp, os.path.join(library_dir(), slug + ".json"))
    return slug


def library_load(slug):
    with open(os.path.join(library_dir(), slugify(slug) + ".json"), "r", encoding="utf-8") as f:
        return Design.from_json(json.load(f))


def library_delete(slug):
    try:
        os.remove(os.path.join(library_dir(), slugify(slug) + ".json"))
    except OSError:
        pass


def library_list():
    """Saved designs on this computer, newest first: [dict(name, slug, size, blocks, mtime)]."""
    out = []
    try:
        names = os.listdir(library_dir())
    except OSError:
        return out
    for fn in names:
        if not fn.endswith(".json"):
            continue
        path = os.path.join(library_dir(), fn)
        try:
            with open(path, "r", encoding="utf-8") as f:
                des = Design.from_json(json.load(f))
            out.append({"name": des.name, "slug": fn[:-5], "size": (des.w, des.d, des.h),
                        "blocks": build_run(des)[1], "mtime": os.path.getmtime(path)})
        except Exception:
            continue
    out.sort(key=lambda e: -e["mtime"])
    return out


def unique_name(base, taken_slugs):
    base = clean_name(base)
    n, name = 1, base
    while slugify(name) in taken_slugs:
        n += 1
        name = "%s %d" % (base[:26], n)
    return name


def load_config():
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_config(cfg):
    try:
        os.makedirs(CONFIG_DIR, exist_ok=True)
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2)
        try:
            os.chmod(CONFIG_FILE, 0o600)      # may hold a token if the user opted in
        except OSError:
            pass
    except OSError:
        pass


def import_old_design():
    """Version 1 kept one 'last design' file; bring it into the list the first time."""
    if library_list():
        return
    try:
        with open(LAST_DESIGN_FILE, "r", encoding="utf-8") as f:
            library_save(Design.from_json(json.load(f)))
    except Exception:
        pass
# ============================================================ vanilla item colours (generated by tools_make_palette.py)
# name=kind + average, dark, light and accent colour measured from the game's textures (kind: b block, i item).
# Only these numbers are kept; the app draws its own simplified tiles from them.
ICON_DATA = (
    "acacia_boat=i7e4426,4b2615,b9683a,c57441;acacia_button=ba85a32,914c2a,bd673a,ba6337;acacia_chest_boat=i754723,"
    "392514,b66b35,b77330;acacia_door=ia35f3c,865036,b16640,b16640;acacia_fence=ba85a32,914c2a,bd673a,ba6337;acacia"
    "_fence_gate=ba85a32,914c2a,bd673a,ba6337;acacia_hanging_sign=i824c2d,472a16,b36135,be683b;acacia_leaves=b569e3"
    "9,3c6f28,6cbe48,569e39;acacia_log=b965837,704d38,b66135,ba6337;acacia_planks=ba85a32,914c2a,bd673a,ba6337;acac"
    "ia_pressure_plate=ba85a32,914c2a,bd673a,ba6337;acacia_sapling=b767517,74570e,78911e,7e9821;acacia_sign=i854c2b"
    ",452b15,ad633b,bc6639;acacia_slab=ba85a32,914c2a,bd673a,ba6337;acacia_stairs=ba85a32,914c2a,bd673a,ba6337;acac"
    "ia_trapdoor=b9c5733,80472c,b96b40,c87243;acacia_wood=b676056,575148,766f64,766f64;activator_rail=b73574a,4d0b0"
    "7,9f9686,620202;allay_spawn_egg=ibcbcbc,7c7c7c,e7e7e7,e7e7e7;allium=b9e89b7,5f765d,d7b0f8,a65ee1;amethyst_bloc"
    "k=b8561bf,64469f,ae81e3,a678f1;amethyst_cluster=ba37ecf,7052ab,e0b4ec,a27ee2;amethyst_shard=i9370c0,5d4095,dbb"
    "2eb,b38ef3;ancient_debris=b5e423a,391a12,8b756e,562e26;andesite=b888888,777777,999998,999998;andesite_slab=b88"
    "8888,777777,999998,999998;andesite_stairs=b888888,777777,999998,999998;andesite_wall=b888888,777777,999998,999"
    "998;angler_pottery_sherd=i6e3d32,4f2b23,8e4f40,9f5949;anvil=b484848,3f3f3f,515151,515151;apple=iaf1d1f,77170c,"
    "ec2a36,ff1c2b;archer_pottery_sherd=i6a3b30,4c2820,8c4e3f,9f5949;armadillo_scute=i975e5b,6f3b3c,bc807b,965954;a"
    "rmadillo_spawn_egg=ibcbcbc,7c7c7c,e7e7e7,e7e7e7;armor_stand=i715d3d,40321f,a98f68,b4905a;arms_up_pottery_sherd"
    "=i6a3b31,4f2b23,894c3e,9e5848;arrow=i7b7364,322c21,cfcfcf,896727;axolotl_bucket=ia1839c,493e63,eac8df,614fb7;a"
    "xolotl_spawn_egg=ibcbcbc,7c7c7c,e7e7e7,e7e7e7;azalea=b5d752d,4b6229,6e8d2e,70922d;azalea_leaves=b5a722c,425728"
    ",6f8d2d,70922d;azure_bluet=ba9cc7f,519d2c,ebf1f1,ffec4f;baked_potato=iaf812d,884f09,dbaf49,c49428;bamboo=i567b"
    "20,446319,6d9732,5c8718;bamboo_block=b8b8d3e,616c25,afae55,bcbf54;bamboo_button=bc1ad50,a18e42,ddc662,d3bb50;b"
    "amboo_chest_raft=i705d2a,352a17,b6963f,b07f2e;bamboo_door=ibeab4f,a39244,dbc45f,d3bb50;bamboo_fence=bceba59,b6"
    "a549,e4ce6d,d1b94f;bamboo_fence_gate=bceb954,c2ae4c,dcc562,d3bb50;bamboo_hanging_sign=ia1914b,433f2f,e0c967,ce"
    "b64e;bamboo_mosaic=bbeaa4e,9f8c41,d9c25c,d3bb50;bamboo_mosaic_slab=bbeaa4e,9f8c41,d9c25c,d3bb50;bamboo_mosaic_"
    "stairs=bbeaa4e,9f8c41,d9c25c,d3bb50;bamboo_planks=bc1ad50,a18e42,ddc662,d3bb50;bamboo_pressure_plate=bc1ad50,a"
    "18e42,ddc662,d3bb50;bamboo_raft=i8c7e3d,494124,dac25e,e5cd67;bamboo_sign=iae9b49,625726,dfc866,d1b94f;bamboo_s"
    "lab=bc1ad50,a18e42,ddc662,d3bb50;bamboo_stairs=bc1ad50,a18e42,ddc662,d3bb50;bamboo_trapdoor=bc6b355,a99846,e2c"
    "b6a,d1b94f;barrel=b735530,5f4627,846238,886539;barrier=id40000,b70000,e30000,e30000;basalt=b505156,2e323e,6d6d"
    "6d,6d6d6d;bat_spawn_egg=ibcbcbc,7c7c7c,e7e7e7,e7e7e7;bedrock=b555555,2f2f2f,808080,808080;bee_nest=ba07f57,725"
    "438,c7a470,c8a671;bee_spawn_egg=ibcbcbc,7c7c7c,e7e7e7,e7e7e7;beef=ib73b33,73130e,e3685d,e03e35;beehive=bb4925a"
    ",a5864e,c09b61,c29d62;beetroot=i882b2a,5f1b14,b24449,a4272c;beetroot_seeds=i866d47,55452b,c59e69,deb075;beetro"
    "ot_soup=i57280d,2d1f06,7d3614,a92426;bell=ic19940,693617,fef177,fdd537;big_dripleaf=b6f8d33,54692e,86ab3c,8bb2"
    "3d;birch_boat=i9b8d61,61533b,d5c78a,c8b77a;birch_button=bc0af79,a7966a,d7c588,d7c185;birch_chest_boat=i857246,"
    "40321e,ccbd81,a57123;birch_door=icfc7a1,aea16e,eae8de,d6ca8c;birch_fence=bc0af79,a7966a,d7c588,d7c185;birch_fe"
    "nce_gate=bc0af79,a7966a,d7c588,d7c185;birch_hanging_sign=i92845c,433a2b,cdbc7f,cfbc7f;birch_leaves=b509435,386"
    "725,65b243,509435;birch_log=bc1b387,9c9170,e1d3ab,d7c185;birch_planks=bc0af79,a7966a,d7c588,d7c185;birch_press"
    "ure_plate=bc0af79,a7966a,d7c588,d7c185;birch_sapling=b7fa04f,567a30,bfcb87,6c9e38;birch_sign=i9f9166,4f4126,d2"
    "c495,d0bc7f;birch_slab=bc0af79,a7966a,d7c588,d7c185;birch_stairs=bc0af79,a7966a,d7c588,d7c185;birch_trapdoor=b"
    "cfc29d,9d8a60,f5efdf,d7c286;birch_wood=bd8d7d2,a6a39b,fbfbfa,fbfbfa;black_bed=b141519,0b0d12,1d1d21,1d1d21;bla"
    "ck_candle=i2b2941,14131d,47436b,4d4781;black_carpet=b141519,0b0d12,1d1d21,1d1d21;black_concrete=b080a0f,07090e"
    ",090b10,090b10;black_concrete_powder=b191a1f,111319,222327,222327;black_dye=i1b1a28,09080c,312f49,403e5e;black"
    "_glazed_terracotta=b431e20,101012,882324,992222;black_shulker_box=b19191d,101116,1f1f23,1f1f23;black_stained_g"
    "lass=b191919,191919,191919,191919;black_stained_glass_pane=b191919,191919,191919,191919;black_terracotta=b2516"
    "10,24150f,261711,261711;black_wool=b141519,0b0d12,1d1d21,1d1d21;blackstone=b2a2429,1c1216,383441,383441;blacks"
    "tone_slab=b2a2429,1c1216,383441,383441;blackstone_stairs=b2a2429,1c1216,383441,383441;blackstone_wall=b2a2328,"
    "1c1117,393541,393541;blade_pottery_sherd=i6e3d32,4f2b23,8e4f40,9f5949;blast_furnace=b6b6b6b,434344,989997,9899"
    "97;blaze_powder=ibf7013,953300,fdd239,ffaf00;blaze_rod=ic4861a,af4b02,e9cf31,ffdf1b;blaze_spawn_egg=ibcbcbc,7c"
    "7c7c,e7e7e7,e7e7e7;blue_bed=b35399d,2f3193,3b42a8,3d4bb0;blue_candle=i3a51a3,2d3b81,486bc4,4573c7;blue_carpet="
    "b35399d,2f3193,3b42a8,3d4bb0;blue_concrete=b2c2e8f,2c2e8e,2d2f90,2c2e8f;blue_concrete_powder=b4649a6,40429e,4c"
    "50af,4d52b5;blue_dye=i2b52a4,082769,5a81de,345ec3;blue_glazed_terracotta=b2f408b,221d43,3a6fc6,2985c9;blue_ice"
    "=b74a7fd,6b9efb,82b2fe,6ca3fd;blue_orchid=b2fa2a8,318b52,29b9f9,2abffd;blue_shulker_box=b2b2d8c,222377,32359a,"
    "32359a;blue_stained_glass=b334cb2,334cb2,334cb2,334cb2;blue_stained_glass_pane=b334cb2,334cb2,334cb2,334cb2;bl"
    "ue_terracotta=b4a3b5b,493a59,4b3d5c,4b3d5c;blue_wool=b35399d,2f3193,3b42a8,3d4bb0;bogged_spawn_egg=ibcbcbc,7c7"
    "c7c,e7e7e7,e7e7e7;bolt_armor_trim_smithing_template=i9a634c,793822,ad917c,5fb4b2;bone=icbcab7,898b75,fcfcf2,fc"
    "fcf2;bone_block=bd1ceb3,c3bfa1,e3e0ca,e3e0ca;bone_meal=i9e9eb3,535276,eeeef0,59557f;book=i5a4629,2c1c05,8a7e65"
    ",654b17;bookshelf=b755e3b,5d2312,af8f57,a53011;bow=i504227,32250e,78643f,896727;bowl=i463009,2c1d04,63440c,714"
    "f0f;brain_coral=bc55498,a03179,e37eb6,d6549b;brain_coral_block=bcf5b9f,b63e8b,e27ab5,d6549b;brain_coral_fan=bc"
    "a5499,b13d87,de70ae,d6549b;bread=i8a651d,553f13,b98726,bc8927;breeze_rod=i6c79a8,3a5a85,a69dc9,2f527f;breeze_s"
    "pawn_egg=ibcbcbc,7c7c7c,e7e7e7,e7e7e7;brewer_pottery_sherd=i6b3b30,4b2820,8d4f40,9f5949;brewing_stand=i76694f,"
    "444444,c2994b,ce752f;brick=i85412e,4c251a,bb5c41,c76245;brick_slab=b966153,824838,ac7a6d,bb654f;brick_stairs=b"
    "966153,824838,ac7a6d,bb654f;brick_wall=b966153,824838,ac7a6d,bb654f;bricks=b966153,824838,ac7a6d,bb654f;brown_"
    "bed=b724728,663f22,7e502f,825331;brown_candle=i784c2d,533422,a5693f,bc7949;brown_carpet=b724728,663f22,7e502f,"
    "825331;brown_concrete=b603b1f,5f3b1f,613c20,603b1f;brown_concrete_powder=b7d5435,734e30,885c3c,8f623f;brown_dy"
    "e=i6c3a16,421f05,985c32,bd7746;brown_glazed_terracotta=b776a55,47574e,b98464,167e90;brown_mushroom=b99745c,695"
    "03f,cc9978,cc9978;brown_mushroom_block=b956f51,926b51,977251,977251;brown_shulker_box=b6a4223,5f3a1e,724728,73"
    "4828;brown_stained_glass=b664c33,664c33,664c33,664c33;brown_stained_glass_pane=b664c33,664c33,664c33,664c33;br"
    "own_terracotta=b4d3323,4c3122,4e3424,4f3423;brown_wool=b724728,663f22,7e502f,825331;brush=ia67e62,6a4829,e6b59"
    "6,a75d32;bubble_coral=ba1179f,76077f,c924bb,c819ba;bubble_coral_block=ba51aa2,88118b,c521b8,c819ba;bubble_cora"
    "l_fan=ba0209f,770780,c63eba,a51da5;bucket=i777777,353535,bcbcbc,bcbcbc;budding_amethyst=b8460ba,5a3c94,b98ae6,"
    "a678f1;bundle=i734022,462206,ac6a3e,c3723f;burn_pottery_sherd=i6d3d32,4e2b23,8e4f40,9f5949;cactus=b58822d,4164"
    "1e,709c40,649832;cake=icfa78f,8e381e,fef9ec,d4452d;calcite=bdfe0dc,cacbc7,f2f3f1,f2f3f1;calibrated_sculk_senso"
    "r=b0d3d48,06262d,1a6375,1d7589;camel_spawn_egg=ibcbcbc,7c7c7c,e7e7e7,e7e7e7;campfire=i946932,49371f,d2ab5d,c96"
    "c03;candle=id8bc82,ab8349,fdebc1,ac7a38;carrot=i787113,304902,bea02a,fa8a09;carrot_on_a_stick=i5f4a29,342914,9"
    "17343,d26c0b;cartography_table=b432b14,301e0e,543719,5e3e1b;carved_pumpkin=b965411,3d0d01,dd8f24,e3901d;cat_sp"
    "awn_egg=ibcbcbc,7c7c7c,e7e7e7,e7e7e7;cauldron=i3c3b3e,26262b,525151,525151;cave_spider_spawn_egg=ibcbcbc,7c7c7"
    "c,e7e7e7,e7e7e7;chain=i313849,252c3d,42495b,42495b;chain_command_block=b819c90,57695f,b1bcbd,7e8b75;chainmail_"
    "boots=i616161,1b1b1b,c0c0c0,c0c0c0;chainmail_chestplate=i7c7c7c,232323,cbcbcb,cbcbcb;chainmail_helmet=i5b5b5b,"
    "191919,bdbdbd,bdbdbd;chainmail_leggings=i676767,1a1a1a,c1c1c1,c1c1c1;charcoal=i27231b,16140f,3f372b,3f372b;che"
    "rry_boat=id19591,b16265,e9c2bc,9a464f;cherry_button=be2b2ac,d99a94,e7c5bf,cd8580;cherry_chest_boat=ia37562,513"
    "520,e6bbb4,a57123;cherry_door=idda7a1,d08a85,e6c1ba,cb817c;cherry_fence=be2b2ac,d99a94,e7c5bf,cd8580;cherry_fe"
    "nce_gate=be2b2ac,d99a94,e7c5bf,cd8580;cherry_hanging_sign=ib77b7e,784f51,db979d,c27172;cherry_leaves=be5acc2,c"
    "38887,f8d1ea,a58855;cherry_log=bb98d89,613e43,e6bcb2,d18b86;cherry_planks=be2b2ac,d99a94,e7c5bf,cd8580;cherry_"
    "pressure_plate=be2b2ac,d99a94,e7c5bf,cd8580;cherry_sapling=ba4758f,2c1924,f6c3e2,eb92be;cherry_sign=ic18d8a,7e"
    "4348,e7bdb7,b56366;cherry_slab=be2b2ac,d99a94,e7c5bf,cd8580;cherry_stairs=be2b2ac,d99a94,e7c5bf,cd8580;cherry_"
    "trapdoor=be2b2ac,da9b95,e6c7c0,d4928d;cherry_wood=b36212c,2a1823,442a36,442a36;chest_minecart=i645944,262723,9"
    "e8765,a76e1f;chicken=icd9d8b,a26b58,f4ccbe,ba8269;chicken_spawn_egg=ibcbcbc,7c7c7c,e7e7e7,e7e7e7;chipped_anvil"
    "=b484848,3b3b3b,595959,595959;chiseled_bookshelf=bb29058,9b7d48,c6a167,c29d62;chiseled_copper=bb86449,984f36,d"
    "4785d,db7d61;chiseled_deepslate=b363636,252525,48494b,48494b;chiseled_nether_bricks=b2f171c,1c0e11,402026,4020"
    "26;chiseled_polished_blackstone=b353038,22191c,494650,494650;chiseled_quartz_block=be7e2d9,ddd9cb,efebe7,efebe"
    "7;chiseled_red_sandstone=bb5611f,ad5c1b,bc6622,c06822;chiseled_sandstone=bdfd6aa,dbcfa3,e3dbb1,dbcda0;chiseled"
    "_stone_bricks=b777677,5d5d5d,928f92,928f92;chiseled_tuff=b5d625b,484d43,787972,787972;chiseled_tuff_bricks=b6e"
    "716a,585f5a,838278,838278;chorus_flower=b977897,542d54,eeddef,714871;chorus_fruit=i7e5d7d,522b51,b498b3,5e2e5c"
    ";chorus_plant=b5d395d,451f45,7a5a7a,7a5a7a;clay=ba0a6b3,9aa0ad,a8acbb,a8acbb;clay_ball=i737a8b,3f4356,a4aab8,5"
    "e6c8d;clock=ib18f3f,503f62,fbe849,f5de08;coal=i232124,18151b,2e2f2f,2e2f2f;coal_block=b100f0f,060606,181818,18"
    "1818;coal_ore=b696969,454544,838383,838383;coarse_dirt=b77553b,533a28,9b7150,b7835b;coast_armor_trim_smithing_"
    "template=i5e686e,2f303a,8fa4a7,3b8694;cobbled_deepslate=b4d4d50,39393e,676767,676767;cobbled_deepslate_slab=b4"
    "d4d50,39393e,676767,676767;cobbled_deepslate_stairs=b4d4d50,39393e,676767,676767;cobbled_deepslate_wall=b4d4d5"
    "0,39393e,676767,676767;cobblestone=b7f7f7f,616060,a1a0a1,a1a0a1;cobblestone_slab=b7f7f7f,616060,a1a0a1,a1a0a1;"
    "cobblestone_stairs=b7f7f7f,616060,a1a0a1,a1a0a1;cobblestone_wall=b7f7f7f,616060,a1a0a1,a1a0a1;cobweb=be4e9ea,c"
    "7d1d4,ffffff,ffffff;cocoa_beans=i56341b,301a0a,815333,976746;cod=ia6815b,7e563b,cbae85,b18953;cod_bucket=i817c"
    "7d,373945,c7beb2,4363c7;cod_spawn_egg=ibcbcbc,7c7c7c,e7e7e7,e7e7e7;command_block=bad836a,825435,c0b3b3,bf7140;"
    "command_block_minecart=i695d52,23221b,b19a89,c47c46;comparator=i775246,640707,a49d8c,850404;compass=i544e4e,22"
    "2121,9d9898,612d2d;composter=b70461f,47260a,966437,a56d3b;conduit=b9f8b71,6f6042,bcb19d,b4886b;cooked_beef=i60"
    "3525,3a1e13,89503a,985c43;cooked_chicken=ib1704a,783a19,dfa785,cd7d4a;cooked_cod=ib59877,916949,d9cdb1,be9865;"
    "cooked_mutton=i744534,422417,9e6851,9d6147;cooked_porkchop=iad9665,7b6130,d8c797,8c6932;cooked_rabbit=iaa7350,"
    "663317,e2b595,a95f32;cooked_salmon=i775337,3c392e,a77751,ba4f23;cookie=ib57038,693b1f,e7974f,d9833e;copper_blo"
    "ck=bc06b4f,a4583e,d97c61,d67b5b;copper_bulb=b9c5639,693a1a,d0765a,dc7e63;copper_door=ib86a4e,8d533e,d67b5b,d67"
    "b5b;copper_grate=bbf6b4f,a3573d,d87c5f,d67b5b;copper_ingot=ib65c3e,8b4027,e88160,e77c56;copper_ore=b7c7d78,626"
    "c69,90908a,937d5f;copper_trapdoor=bbe6a4f,9c5239,de7f65,d67b5b;cornflower=b4f7992,345e70,658fb4,466aeb;cow_spa"
    "wn_egg=ibcbcbc,7c7c7c,e7e7e7,e7e7e7;cracked_deepslate_bricks=b404041,292929,5b5b5c,5b5b5c;cracked_deepslate_ti"
    "les=b343434,262626,454546,454546;cracked_nether_bricks=b281417,180c0f,381a20,381a20;cracked_polished_blackston"
    "e_bricks=b2c252b,1b1116,3e3a46,3e3a46;cracked_stone_bricks=b767576,606060,8a898a,8a898a;crafter=b4e4e4e,3e3e3d"
    ",606060,606060;crafting_table=b816946,2d1e11,c2a77d,c09b60;creeper_banner_pattern=ic3bca9,8d7e5d,ebebeb,7a6546"
    ";creeper_spawn_egg=ibcbcbc,7c7c7c,e7e7e7,e7e7e7;crimson_button=b653046,472333,813b57,863e5a;crimson_door=i7839"
    "52,52293a,954564,ae4b71;crimson_fence=b653046,472333,813b57,863e5a;crimson_fence_gate=b653046,472333,813b57,86"
    "3e5a;crimson_fungus=b8d2c1d,5d0707,cd5a32,ff6500;crimson_hanging_sign=i653448,42202f,7f435b,8f405e;crimson_hyp"
    "hae=b5d1a1e,600f0a,6e1f29,941313;crimson_nylium=b6b1a1a,610404,862b2b,aa2223;crimson_planks=b653046,472333,813"
    "b57,863e5a;crimson_pressure_plate=b653046,472333,813b57,863e5a;crimson_roots=b7e0829,580628,a30c25,ad101c;crim"
    "son_sign=i682c42,471925,813b57,8b2e43;crimson_slab=b653046,472333,813b57,863e5a;crimson_stairs=b653046,472333,"
    "813b57,863e5a;crimson_stem=b703146,58222c,843c59,91232e;crimson_trapdoor=b673248,4d2838,893e5b,924160;crossbow"
    "=i51361d,2a1908,7d5a37,905820;crying_obsidian=b200a3c,020105,471578,6e06c1;cut_copper=bbf6a50,a2563d,de7f66,d6"
    "7b5b;cut_copper_slab=bbf6a50,a2563d,de7f66,d67b5b;cut_copper_stairs=bbf6a50,a2563d,de7f66,d67b5b;cut_red_sands"
    "tone=bb5611f,ad5c1b,bc6622,c06822;cut_red_sandstone_slab=bb5611f,ad5c1b,bc6622,c06822;cut_sandstone=bdfd6aa,db"
    "cfa3,e3dbb1,dbcda0;cut_sandstone_slab=bdfd6aa,dbcfa3,e3dbb1,dbcda0;cyan_bed=b158991,157d8b,159698,169a9b;cyan_"
    "candle=i118283,10565a,13b0af,15c4c4;cyan_carpet=b158991,157d8b,159698,169a9b;cyan_concrete=b157788,157687,1678"
    "89,157788;cyan_concrete_powder=b24939d,238996,25a0a5,27aaae;cyan_dye=i236a88,114b63,3a8bad,479bbd;cyan_glazed_"
    "terracotta=b34767d,3b4043,4ab0b0,17acac;cyan_shulker_box=b147987,106676,168691,168792;cyan_stained_glass=b4c7f"
    "99,4c7f99,4c7f99,4c7f99;cyan_stained_glass_pane=b4c7f99,4c7f99,4c7f99,4c7f99;cyan_terracotta=b565b5b,545859,59"
    "5d5c,595d5c;cyan_wool=b158991,157d8b,159698,169a9b;damaged_anvil=b484848,393939,5a5a5a,5a5a5a;dandelion=b93ac2"
    "b,217f0b,fee94c,f5b02b;danger_pottery_sherd=i6c3c31,4e2a22,8d4f40,9f5949;dark_oak_boat=i452b13,2a180c,65411f,7"
    "74c24;dark_oak_button=b422b14,321f0e,503418,53381a;dark_oak_chest_boat=i523818,2a1a0b,835a21,a57123;dark_oak_d"
    "oor=i462e17,32210f,593d20,66461c;dark_oak_fence=b422b14,321f0e,503418,53381a;dark_oak_fence_gate=b422b14,321f0"
    "e,503418,53381a;dark_oak_hanging_sign=i4f3a23,302113,735d40,ae8c52;dark_oak_leaves=b579f3a,3c6f28,6cbf48,579f3"
    "a;dark_oak_log=b432d16,372411,4d3319,4f3318;dark_oak_planks=b422b14,321f0e,503418,53381a;dark_oak_pressure_pla"
    "te=b422b14,321f0e,503418,53381a;dark_oak_sapling=b3d5a1e,294411,537c30,4c9f37;dark_oak_sign=i51381d,31200f,795"
    "a32,b9975a;dark_oak_slab=b422b14,321f0e,503418,53381a;dark_oak_stairs=b422b14,321f0e,503418,53381a;dark_oak_tr"
    "apdoor=b4b3117,382510,5d3d1e,714924;dark_oak_wood=b3c2e1a,2f2413,47371f,503d22;dark_prismarine=b335b4b,2a4439,"
    "3c7762,3b8268;dark_prismarine_slab=b335b4b,2a4439,3c7762,3b8268;dark_prismarine_stairs=b335b4b,2a4439,3c7762,3"
    "b8268;daylight_detector=b423723,362d1d,514129,56452b;dead_brain_coral=b857d78,746a66,9a9490,9a9490;dead_brain_"
    "coral_block=b7c7572,63605f,968f8a,968f8a;dead_brain_coral_fan=b847d79,6b6360,9e9994,9e9994;dead_bubble_coral=b"
    "847c78,6c6461,9b9690,9b9690;dead_bubble_coral_block=b837b77,6f6764,99928d,99928d;dead_bubble_coral_fan=b8c8682"
    ",6d6562,a29d99,a29d99;dead_bush=b6b4e28,513d24,8c612a,a06d2e;dead_fire_coral=b88807c,746a66,9e9994,9e9994;dead"
    "_fire_coral_block=b837b77,6d6664,99938e,99938e;dead_fire_coral_fan=b7c7672,5d5a59,98928d,98928d;dead_horn_cora"
    "l=b8e8781,7e7571,9c9691,9c9691;dead_horn_coral_block=b857e7a,6c6562,9f9b96,9f9b96;dead_horn_coral_fan=b867d79,"
    "6f6663,9c9791,9c9791;dead_tube_coral=b766f6b,605c5b,8d8580,8d8580;dead_tube_coral_block=b827b77,686362,99938e,"
    "99938e;dead_tube_coral_fan=b807a76,65615f,9d9892,9d9892;debug_stick=i4b3815,281e0b,785a22,896727;deepslate=b57"
    "5759,434348,6a6a6a,6a6a6a;deepslate_brick_slab=b464647,2e2e2e,5f5f5f,5f5f5f;deepslate_brick_stairs=b464647,2e2"
    "e2e,5f5f5f,5f5f5f;deepslate_brick_wall=b464647,2e2e2e,5f5f5f,5f5f5f;deepslate_bricks=b464647,2e2e2e,5f5f5f,5f5"
    "f5f;deepslate_coal_ore=b4a4a4c,28282c,6b6b6b,6b6b6b;deepslate_copper_ore=b5c5d59,3d3d42,827b6d,937d5f;deepslat"
    "e_diamond_ore=b536a6a,3d3f43,679f9c,2bbab9;deepslate_emerald_ore=b4e6857,304239,619d74,23d45d;deepslate_gold_o"
    "re=b73664e,3f3f44,ac9558,eda615;deepslate_iron_ore=b6a635e,404044,98887c,c49f85;deepslate_lapis_ore=b4f5a73,2b"
    "3f6b,6a7693,1c4dbe;deepslate_redstone_ore=b68494a,473135,7d6868,e81e1e;deepslate_tile_slab=b363637,272727,4848"
    "49,484849;deepslate_tile_stairs=b363637,272727,484849,484849;deepslate_tile_wall=b363637,272727,484849,484849;"
    "deepslate_tiles=b363637,272727,484849,484849;detector_rail=b7b685a,582f20,a29c91,721e13;diamond=i54bdb4,14716f"
    ",bdfbf0,21c7b7;diamond_axe=i306047,182518,39b796,31e5c5;diamond_block=b62ede4,31d7d8,97fdef,12bfc3;diamond_boo"
    "ts=i2a7f74,082722,62ebd9,20c5b5;diamond_chestplate=i38a699,0b322b,70f2e0,20c5b5;diamond_helmet=i23756b,082520,"
    "51e3d1,20c5b5;diamond_hoe=i385034,1d2213,509269,2cceb2;diamond_horse_armor=i5ec499,25a192,91f4de,adbe1f;diamon"
    "d_leggings=i2a867b,082621,60ebd9,20c5b5;diamond_ore=b798d8c,667373,83b2b0,31bdbc;diamond_pickaxe=i2f533b,13221"
    "8,45a17d,2dd3b6;diamond_shovel=i34654a,192216,33cdae,33ebcb;diamond_sword=i276b5c,0b2821,51d5bd,33ebcb;diorite"
    "=bbcbcbc,959494,e3e3e4,e3e3e4;diorite_slab=bbcbcbc,959494,e3e3e4,e3e3e4;diorite_stairs=bbcbcbc,959494,e3e3e4,e"
    "3e3e4;diorite_wall=bbcbcbc,959494,e3e3e4,e3e3e4;dirt=b866043,6c4b33,a57855,b9855c;dirt_path=b866043,6c4b33,a57"
    "855,b9855c;disc_fragment_5=i2b3b3e,0d1217,485f5f,027a79;dispenser=b7a7979,454343,aeaeae,aeaeae;dolphin_spawn_e"
    "gg=ibcbcbc,7c7c7c,e7e7e7,e7e7e7;donkey_spawn_egg=ibcbcbc,7c7c7c,e7e7e7,e7e7e7;dragon_breath=ib9a0bd,836894,e4d"
    "bec,b34b39;dragon_egg=b0c090f,08080c,150c17,220228;dried_kelp=i312c24,141210,50493b,50493b;dried_kelp_block=b2"
    "6301d,162013,3a452e,3a452e;dripstone_block=b866b5c,71534e,98826a,a08d71;dropper=b7a7979,454444,aeaeae,aeaeae;d"
    "rowned_spawn_egg=ibcbcbc,7c7c7c,e7e7e7,e7e7e7;dune_armor_trim_smithing_template=ib2b48a,908651,d3e2c1,44c0c9;e"
    "cho_shard=i09343d,0e161b,065d6a,068c93;egg=iaa9d77,675f47,e1d1a0,dfce9b;elder_guardian_spawn_egg=ibcbcbc,7c7c7"
    "c,e7e7e7,e7e7e7;elytra=i5e5e66,3b3b3b,818190,818190;emerald=i2da64f,004803,7ff5ac,17dd62;emerald_block=b2acb57"
    ",1aa932,4eee8a,17dd62;emerald_ore=b6c8873,4e7253,79aa8b,23d45d;enchanted_book=i654229,301c06,947a5b,bc3d2d;enc"
    "hanted_golden_apple=ibd8c28,762e07,edde5f,dba213;enchanting_table=b0f0a18,010003,221834,36244e;end_crystal=ib5"
    "91c2,8e3289,dae5ed,c01f5a;end_portal_frame=b96a37a,244748,e1e7a5,d0d18e;end_rod=bcfc6bb,89807c,fef9f0,fbeace;e"
    "nd_stone=bdbde9e,cdc98d,ecf4b2,d5da94;end_stone_brick_slab=bdae0a2,c4c189,eaf6b4,ecfbaf;end_stone_brick_stairs"
    "=bdae0a2,c4c189,eaf6b4,ecfbaf;end_stone_brick_wall=bdae0a2,c4c189,eaf6b4,ecfbaf;end_stone_bricks=bdae0a2,c4c18"
    "9,eaf6b4,ecfbaf;ender_dragon_spawn_egg=ibcbcbc,7c7c7c,e7e7e7,e7e7e7;ender_eye=i487858,193c31,7bb368,93ca5b;end"
    "er_pearl=i14584d,032a24,2e9483,46c5af;enderman_spawn_egg=ibcbcbc,7c7c7c,e7e7e7,e7e7e7;endermite_spawn_egg=ibcb"
    "cbc,7c7c7c,e7e7e7,e7e7e7;evoker_spawn_egg=ibcbcbc,7c7c7c,e7e7e7,e7e7e7;experience_bottle=i8da342,423304,def174"
    ",b6e45a;explorer_pottery_sherd=i67392f,4b2820,894c3e,9f5949;exposed_chiseled_copper=b9a7764,796856,b98676,ce8d"
    "83;exposed_copper=ba17d67,89715b,b98778,ce8d83;exposed_copper_bulb=b876b59,5f5243,b68372,ce8d83;exposed_copper"
    "_door=i967664,6f6251,ba8277,b37e6f;exposed_copper_grate=ba17d68,88715a,be877a,ce8d83;exposed_copper_trapdoor=b"
    "a17d68,806f57,c5887e,ce8d83;exposed_cut_copper=b9a7965,7c6c55,b98777,ce8d83;exposed_cut_copper_slab=b9a7965,7c"
    "6c55,b98777,ce8d83;exposed_cut_copper_stairs=b9a7965,7c6c55,b98777,ce8d83;eye_armor_trim_smithing_template=ib8"
    "bf8e,8c886c,d3edb5,62dae0;farmland=b866043,6c4b33,a57855,b9855c;feather=icfcfcf,a5a5a5,f4f4f4,f4f4f4;fermented"
    "_spider_eye=i671027,330319,982536,9d1e2d;fern=b4f913a,376528,63ae48,4f913a;filled_map=id5d5aa,989943,fcfcf2,a7"
    "a848;fire_charge=i5c4229,2e1f18,8d6a41,be690a;fire_coral=ba6252e,791a26,d33336,e23f36;fire_coral_block=ba3232e"
    ",811b27,c82c36,d43436;fire_coral_fan=b9e222d,791a26,c72e35,df3c36;firework_rocket=i9e5251,5e1a15,cdb7b9,c02929"
    ";firework_star=i575757,3b3b3b,797979,797979;fishing_rod=i584f3d,312714,908674,7e5e24;fletching_table=bad9b6f,7"
    "5603f,dcca97,cfb274;flint=i323131,171616,525252,525252;flint_and_steel=i404040,121212,7a7a7a,7a7a7a;flow_armor"
    "_trim_smithing_template=i7187b4,495c86,92b4d6,59d8db;flow_banner_pattern=ic3bca9,8d7e5d,ebebeb,7a6546;flow_pot"
    "tery_sherd=i67392f,4d2921,844a3c,9a5646;flower_banner_pattern=ic3bca9,8d7e5d,ebebeb,7a6546;flower_pot=i69372a,"
    "491d15,8c5545,794030;flowering_azalea=b6f7149,4c6229,928273,be67d2;flowering_azalea_leaves=b636f3c,425728,8285"
    "55,b173b4;fox_spawn_egg=ibcbcbc,7c7c7c,e7e7e7,e7e7e7;friend_pottery_sherd=i693b30,4c2820,8a4d3f,9f5949;frog_sp"
    "awn_egg=ibcbcbc,7c7c7c,e7e7e7,e7e7e7;frogspawn=b6e5f56,4d3f36,86776f,86776f;furnace=b5b5b5b,212020,999999,9999"
    "99;furnace_minecart=i545656,252724,878a8c,878a8c;ghast_spawn_egg=ibcbcbc,7c7c7c,e7e7e7,e7e7e7;ghast_tear=i7e9b"
    "9b,374b4b,ceebeb,ceebeb;gilded_blackstone=b372a26,1f1519,564639,9b6613;glass=bafd5db,87bdc8,d0eae9,8bc1cd;glas"
    "s_bottle=i95a2bb,717994,bed6ef,be5a37;glass_pane=bafd5db,87bdc8,d0eae9,8bc1cd;glistering_melon_slice=ib86b34,9"
    "33611,e4b26e,de910c;globe_banner_pattern=ic3bca9,8d7e5d,ebebeb,7a6546;glow_berries=i9f752a,5b4d1c,e7a945,e1822"
    "d;glow_ink_sac=i2b6e69,183b3b,4fb3a5,59e2ba;glow_item_frame=iae8a55,7d5b30,e3c185,e6a259;glow_lichen=b708279,6"
    "67771,7c9082,7c9082;glow_squid_spawn_egg=ibcbcbc,7c7c7c,e7e7e7,e7e7e7;glowstone=bab8354,724823,f4d69c,fbda74;g"
    "lowstone_dust=ib47d44,683f1e,f9c06e,ffbc5e;goat_horn=i4e4c49,332e2d,6c6a66,6c6a66;goat_spawn_egg=ibcbcbc,7c7c7"
    "c,e7e7e7,e7e7e7;gold_block=bf6d03d,e8b127,feea59,f9bd23;gold_ingot=idcb342,a5580c,fdf784,e9b115;gold_nugget=ib"
    "a9840,754b0b,faf49b,e4a814;gold_ore=b91856a,6e6c68,bea86b,eda615;golden_apple=ibd8c28,762e07,edde5f,dba213;gol"
    "den_axe=i82681e,35270d,e8c434,e9b115;golden_boots=i9e862b,45320e,efea5f,e9b115;golden_carrot=i8e641b,4d1c06,e4"
    "c342,dba213;golden_chestplate=ibea938,614612,f1f46b,e9b115;golden_helmet=i957c25,3f2e0e,edde4d,e9b115;golden_h"
    "oe=i6e581c,32250c,bc9f2f,e9bd22;golden_horse_armor=ib28025,602208,f0de56,dba213;golden_leggings=ia38a2a,42300e"
    ",efe95d,e9b115;golden_pickaxe=i735c1b,33260c,cbad31,e9b115;golden_shovel=i826f28,33260c,eddf53,e9bd22;golden_s"
    "word=i967f38,412f0f,f5ec85,e2a314;granite=b956755,7a5243,aa7a68,a4705c;granite_slab=b956755,7a5243,aa7a68,a470"
    "5c;granite_stairs=b956755,7a5243,aa7a68,a4705c;granite_wall=b956755,7a5243,aa7a68,a4705c;grass_block=b7e6b41,6"
    "84831,8d9750,65a53b;gravel=b837f7e,736d6c,94908f,94908f;gray_bed=b3e4447,393c40,444b4e,444b4e;gray_candle=i536"
    "165,3e4a4f,69797f,627286;gray_carpet=b3e4447,393c40,444b4e,444b4e;gray_concrete=b36393d,36393d,373a3e,373a3e;g"
    "ray_concrete_powder=b4c5154,484b4f,52575b,52575b;gray_dye=i6f6f6f,494949,929292,929292;gray_glazed_terracotta="
    "b535a5d,35383c,798285,798285;gray_shulker_box=b373a3e,2e3034,3d4245,3d4245;gray_stained_glass=b4c4c4c,4c4c4c,4"
    "c4c4c,4c4c4c;gray_stained_glass_pane=b4c4c4c,4c4c4c,4c4c4c,4c4c4c;gray_terracotta=b392a23,382922,3a2b24,3a2b24"
    ";gray_wool=b3e4447,393c40,444b4e,444b4e;green_bed=b546d1b,4d6120,5d7a17,638418;green_candle=i4f6a15,354516,6f9"
    "717,7daa17;green_carpet=b546d1b,4d6120,5d7a17,638418;green_concrete=b495b24,485a24,4a5c25,495b24;green_concret"
    "e_powder=b61772c,5b6e2f,688129,6c8725;green_dye=i3e5914,263a07,597c25,63862e;green_glazed_terracotta=b758e43,4"
    "e6222,a7bb8a,75a024;green_shulker_box=b4f641f,485a23,546c1c,546d1b;green_stained_glass=b667f33,667f33,667f33,6"
    "67f33;green_stained_glass_pane=b667f33,667f33,667f33,667f33;green_terracotta=b4c532a,4a5128,4d542b,4b5228;gree"
    "n_wool=b546d1b,4d6120,5d7a17,638418;grindstone=b492d15,382310,563518,583618;guardian_spawn_egg=ibcbcbc,7c7c7c,"
    "e7e7e7,e7e7e7;gunpowder=i535353,363636,757575,757575;guster_banner_pattern=ic3bca9,8d7e5d,ebebeb,7a6546;guster"
    "_pottery_sherd=i6c3c31,4d2921,8d4e40,9f5949;hanging_roots=ba1735b,87563d,b78e7a,a77150;hay_block=ba58b0c,90771"
    "0,baa00b,c9ae09;heart_of_the_sea=i166583,0a3453,1f92ae,1ea2ba;heart_pottery_sherd=i66392e,4b2820,874b3d,9e5848"
    ";heartbreak_pottery_sherd=i693a30,4c2820,8a4d3e,9f5949;heavy_core=b52565e,2e2f30,7d8494,7d8494;heavy_weighted_"
    "pressure_plate=bdcdcdc,c6c6c6,eaeaea,eaeaea;hoglin_spawn_egg=ibcbcbc,7c7c7c,e7e7e7,e7e7e7;honey_block=bfbb934,"
    "f8a111,fcd05f,f79909;honey_bottle=ibb9871,b16a3a,d2cfaa,ff9116;honeycomb=ie99923,d86e29,facf29,ea8e16;honeycom"
    "b_block=be5941d,cc6d06,fcc449,e88c08;hopper=i434443,333333,555655,555655;hopper_minecart=i515355,2b2e30,7c7f82"
    ",7c7f82;horn_coral=bd1ba3e,bc9333,e4dc48,ecea4b;horn_coral_block=bd8c742,c7a63b,e9e54b,edec4c;horn_coral_fan=b"
    "cdb73d,bc9b34,dcd542,edec4c;horse_spawn_egg=ibcbcbc,7c7c7c,e7e7e7,e7e7e7;host_armor_trim_smithing_template=i53"
    "473d,332220,716f63,5b9e9e;howl_pottery_sherd=i6c3c31,4f2b23,8c4e3f,9f5949;husk_spawn_egg=ibcbcbc,7c7c7c,e7e7e7"
    ",e7e7e7;ice=b91b7fd,88b0fd,9cbffe,86aefd;infested_chiseled_stone_bricks=b777677,5d5d5d,928f92,928f92;infested_"
    "cobblestone=b7f7f7f,616060,a1a0a1,a1a0a1;infested_cracked_stone_bricks=b767576,606060,8a898a,8a898a;infested_d"
    "eepslate=b575759,434348,6a6a6a,6a6a6a;infested_mossy_stone_bricks=b737969,5c664d,878982,6e844b;infested_stone="
    "b7d7d7d,717171,888888,888888;infested_stone_bricks=b7a797a,636463,8f8d8f,8f8d8f;ink_sac=i494354,272842,72636d,"
    "795c60;iron_axe=i6d6555,271f11,cbcac6,785a22;iron_bars=b888b87,6a6c69,b2b2b2,b2b2b2;iron_block=bdcdcdc,c6c6c6,"
    "eaeaea,eaeaea;iron_boots=i656565,1b1b1b,c7c7c7,c7c7c7;iron_chestplate=i868686,232323,cfcfcf,cfcfcf;iron_door=i"
    "b8b8b8,949494,cdcdcd,cdcdcd;iron_golem_spawn_egg=ibcbcbc,7c7c7c,e7e7e7,e7e7e7;iron_helmet=i5b5b5b,191919,bcbcb"
    "c,bcbcbc;iron_hoe=i5a503f,1a1917,a99b80,896727;iron_horse_armor=i615b5b,301c1c,a1a1a1,3e0404;iron_ingot=i9c9c9"
    "c,565656,e3e3e3,e3e3e3;iron_leggings=i696969,1a1a1a,c4c4c4,c4c4c4;iron_nugget=i858c94,41454a,d7dee6,d7dee6;iro"
    "n_ore=b88817a,736f69,a4958a,c49f85;iron_pickaxe=i5d5544,1d1a13,b7ac9a,836225;iron_shovel=i726959,231c10,e0deda"
    ",896727;iron_sword=i696864,1f1d1a,d0d0d0,4a3817;iron_trapdoor=bcacaca,bcbcbc,d6d5d5,d6d5d5;item_frame=i977349,"
    "734025,c2b07e,a25330;jack_o_lantern=bd69834,a9610f,fcd86e,e3901d;jigsaw=b3e353f,101010,887588,887588;jukebox=b"
    "583a28,30281d,87563c,945d41;jungle_boat=i755239,482f1f,ae805d,b88764;jungle_button=ba07350,7f583a,bb8a67,aa795"
    "4;jungle_chest_boat=i705030,382818,af7e51,a57123;jungle_door=i9c714f,7a573b,b2825e,b2825e;jungle_fence=ba07350"
    ",7f583a,bb8a67,aa7954;jungle_fence_gate=ba07350,7f583a,bb8a67,aa7954;jungle_hanging_sign=i7e5d42,42301d,b07f5b"
    ",aa7954;jungle_leaves=b57a03a,3d7028,6dc048,57a03a;jungle_log=b956d46,695126,b4835f,926a3c;jungle_planks=ba073"
    "50,7f583a,bb8a67,aa7954;jungle_pressure_plate=ba07350,7f583a,bb8a67,aa7954;jungle_sapling=b2f5110,2f3108,31761"
    "c,378020;jungle_sign=i7f5b3a,3e2c14,ae7d59,a67650;jungle_slab=ba07350,7f583a,bb8a67,aa7954;jungle_stairs=ba073"
    "50,7f583a,bb8a67,aa7954;jungle_trapdoor=b986e4d,6e4e36,b78662,b58760;jungle_wood=b554319,423612,66511f,745a24;"
    "kelp=i568027,4d5e19,59a530,59ab30;knowledge_book=i4b7749,20391a,83af83,56ad56;ladder=b7c6036,544125,ab854b,b58"
    "d50;lantern=i927153,42495b,f7c26c,f09149;lapis_block=b1e438c,1a368a,225094,2355a4;lapis_lazuli=i2952a7,0b2f75,"
    "4e76d7,345ec3;lapis_ore=b6b758d,3e578d,8d9098,1c4dbe;large_amethyst_bud=ba17eca,6c4ea6,e4bde9,a27ee2;large_fer"
    "n=b4f913a,376628,63af48,4f913a;lava_bucket=i95806f,4c3732,cbc8af,cf502b;lead=i86502c,5e2f10,aa7450,85461b;leat"
    "her=i8e4226,472112,cc613a,d76b43;leather_boots=i7e7e7e,404040,c1c1c1,c1c1c1;leather_chestplate=i868686,444444,"
    "bcbcbc,bcbcbc;leather_helmet=i666666,363636,a4a4a4,a4a4a4;leather_horse_armor=i867466,382112,cecece,782d00;lea"
    "ther_leggings=i6f6f6f,353535,b8b8b8,b8b8b8;lectern=b957543,725831,b38d53,b58d50;lever=b6f5d43,443622,927d5d,95"
    "7546;light=ifffb1e,fffb1e,fffb1e,fffb1e;light_blue_bed=b3aafd9,2b99ce,48c1e3,258ec9;light_blue_candle=i298dc4,"
    "1f6aa0,3cb0e1,208dcd;light_blue_carpet=b3aafd9,2b99ce,48c1e3,258ec9;light_blue_concrete=b2389c6,2387c5,248ac8,"
    "2389c7;light_blue_concrete_powder=b4ab4d5,3fa6ce,56c3dc,40aad6;light_blue_dye=i5a84c1,2c5286,8db5ee,5082ce;lig"
    "ht_blue_glazed_terracotta=b5ea4d0,285ba9,bae7f2,258ec9;light_blue_shulker_box=b31a3d4,258eca,3ab3da,2691cd;lig"
    "ht_blue_stained_glass=b6699d8,6699d8,6699d8,6699d8;light_blue_stained_glass_pane=b6699d8,6699d8,6699d8,6699d8;"
    "light_blue_terracotta=b716c89,6f6b88,736e8b,736e8b;light_blue_wool=b3aafd9,2b99ce,48c1e3,258ec9;light_gray_bed"
    "=b8e8e86,83837a,999993,999993;light_gray_candle=i7e7e77,585955,a8a69c,918c91;light_gray_carpet=b8e8e86,83837a,"
    "999993,999993;light_gray_concrete=b7d7d73,7c7c72,7d7d73,7d7d73;light_gray_concrete_powder=b9a9a94,909089,a5a59"
    "f,a5a59f;light_gray_dye=i9898a4,494761,cfcfcf,cfcfcf;light_gray_glazed_terracotta=b90a6a7,447e81,cdd1d3,169f9f"
    ";light_gray_shulker_box=b7c7c73,65655d,8b8b82,8b8b82;light_gray_stained_glass=b999999,999999,999999,999999;lig"
    "ht_gray_stained_glass_pane=b999999,999999,999999,999999;light_gray_terracotta=b876a61,85695f,896c63,886a60;lig"
    "ht_gray_wool=b8e8e86,83837a,999993,999993;light_weighted_pressure_plate=bf6d03d,e8b127,feea59,f9bd23;lightning"
    "_rod=bc46f53,a6593f,db7d61,d67b5b;lilac=b9a7d93,5d7b4b,d586dc,439d21;lily_of_the_valley=b7bae5f,3b8217,d9e5d2,"
    "64b132;lily_pad=b317a36,225626,3d9344,317a36;lime_bed=b70b919,64ae18,7dc41d,7bc21a;lime_candle=i6ab01e,4b8615,"
    "91d631,7bc618;lime_carpet=b70b919,64ae18,7dc41d,7bc21a;lime_concrete=b5ea818,5da718,5faa19,5ea918;lime_concret"
    "e_powder=b7dbd29,74b527,86c52d,89c92c;lime_dye=i5c9c17,28541f,85d11d,83d41c;lime_glazed_terracotta=ba2c537,65a"
    "e19,d6e171,f0ad11;lime_shulker_box=b63ac17,519514,70bb18,71bc18;lime_stained_glass=b7fcc19,7fcc19,7fcc19,7fcc1"
    "9;lime_stained_glass_pane=b7fcc19,7fcc19,7fcc19,7fcc19;lime_terracotta=b677534,657332,6a7736,677633;lime_wool="
    "b70b919,64ae18,7dc41d,7bc21a;lingering_potion=ia3a3a3,727272,d6d6d6,d6d6d6;llama_spawn_egg=ibcbcbc,7c7c7c,e7e7"
    "e7,e7e7e7;lodestone=b939598,787878,a9afb6,a9afb6;loom=b4c3c24,362a1a,5c482a,745a34;mace=i515869,232b37,8a92ab,"
    "455b8b;magenta_bed=bbd44b3,b037a6,cb53c3,bd43b2;magenta_candle=ia13298,7b2277,c848b9,cc49b9;magenta_carpet=bbd"
    "44b3,b037a6,cb53c3,bd43b2;magenta_concrete=ba9309f,a82f9e,aa31a0,a82f9e;magenta_concrete_powder=bc053b8,b649ae"
    ",ca60c3,c14db8;magenta_dye=iac55aa,702d78,d678d0,be5cb8;magenta_glazed_terracotta=bd064bf,b63dad,eb97cc,af32a5"
    ";magenta_shulker_box=bad36a3,9d2b93,b93eae,b439aa;magenta_stained_glass=bb24cd8,b24cd8,b24cd8,b24cd8;magenta_s"
    "tained_glass_pane=bb24cd8,b24cd8,b24cd8,b24cd8;magenta_terracotta=b95586c,93556a,985a6e,96566b;magenta_wool=bb"
    "d44b3,b037a6,cb53c3,bd43b2;magma_block=b8d3e1e,4e1b1b,e6711b,e66410;magma_cream=iaa8739,7d2c20,dee261,e8b72a;m"
    "agma_cube_spawn_egg=ibcbcbc,7c7c7c,e7e7e7,e7e7e7;mangrove_boat=i622825,461415,814235,91503d;mangrove_button=b7"
    "53630,662426,844636,8b4d3a;mangrove_chest_boat=i633722,3f1713,915a2d,a57123;mangrove_door=i6f312d,5c2021,7e403"
    "5,8b4c3a;mangrove_fence=b753630,662426,844636,8b4d3a;mangrove_fence_gate=b753630,662426,844636,8b4d3a;mangrove"
    "_hanging_sign=i63332f,451f1c,7a463d,884a38;mangrove_leaves=b509335,386725,64b143,509335;mangrove_log=b66302a,5"
    "d2221,703f32,722f2e;mangrove_planks=b753630,662426,844636,8b4d3a;mangrove_pressure_plate=b753630,662426,844636"
    ",8b4d3a;mangrove_propagule=i60af53,629044,6dc560,58cd5c;mangrove_roots=b4b3b26,3e3122,58462b,5a482c;mangrove_s"
    "ign=i632f29,441d18,7a3d34,824435;mangrove_slab=b753630,662426,844636,8b4d3a;mangrove_stairs=b753630,662426,844"
    "636,8b4d3a;mangrove_trapdoor=b6e2e2a,5f1e1f,834537,8d4f3b;mangrove_wood=b534229,463724,604d2e,675230;map=id5d5"
    "aa,989943,fcfcf2,a7a848;medium_amethyst_bud=b9e78c9,6a4ca4,dfafee,8d6acc;melon=b6f901e,447a1b,9ea81d,a7ac1d;me"
    "lon_seeds=i393017,1e1805,615535,615535;melon_slice=i9b5a2d,6e370e,b39c57,af160b;milk_bucket=i8b8d8d,353535,dde"
    "3e4,a4b9be;minecart=i464d51,232a2f,797f83,797f83;miner_pottery_sherd=i6d3d32,4f2b23,8e4f40,9f5949;mojang_banne"
    "r_pattern=ic3bca9,8d7e5d,ebebeb,7a6546;mooshroom_spawn_egg=ibcbcbc,7c7c7c,e7e7e7,e7e7e7;moss_block=b596d2d,475"
    "c28,6a7f30,6f902d;moss_carpet=b596d2d,475c28,6a7f30,6f902d;mossy_cobblestone=b6e765e,565f43,8c8f86,698047;moss"
    "y_cobblestone_slab=b6e765e,565f43,8c8f86,698047;mossy_cobblestone_stairs=b6e765e,565f43,8c8f86,698047;mossy_co"
    "bblestone_wall=b6e765e,565f43,8c8f86,698047;mossy_stone_brick_slab=b737969,5c664d,878982,6e844b;mossy_stone_br"
    "ick_stairs=b737969,5c664d,878982,6e844b;mossy_stone_brick_wall=b737969,5c664d,878982,6e844b;mossy_stone_bricks"
    "=b737969,5c664d,878982,6e844b;mourner_pottery_sherd=i68392f,4b2820,884c3e,9c5747;mud=b3c393c,333139,444242,444"
    "242;mud_brick_slab=b89674f,6e5345,9c7858,a27d5a;mud_brick_stairs=b89674f,6e5345,9c7858,a27d5a;mud_brick_wall=b"
    "89674f,6e5345,9c7858,a27d5a;mud_bricks=b89674f,6e5345,9c7858,a27d5a;muddy_mangrove_roots=b463a2d,392f2a,524430"
    ",5b492c;mule_spawn_egg=ibcbcbc,7c7c7c,e7e7e7,e7e7e7;mushroom_stem=bcbc4b9,c4beaf,d2cbc3,d2cbc3;mushroom_stew=i"
    "6a4926,2d1f06,c08363,714f0f;music_disc_11=i303030,151515,494949,494949;music_disc_13=i444239,1c1c1c,777256,7d6"
    "b09;music_disc_5=i304145,1b2128,515f60,077674;music_disc_blocks=i413533,1c1c1c,6f4b44,cf4d37;music_disc_cat=i3"
    "4412e,1c1c1c,466f35,3ecd01;music_disc_chirp=i3d2e2f,1c1c1c,593f3f,a30104;music_disc_creator=i58876a,29463a,95c"
    "08f,dbc479;music_disc_creator_music_box=iaa6547,603121,e69a6d,edb364;music_disc_far=i384433,1c1c1c,517744,64e9"
    "35;music_disc_mall=i3a3644,1c1c1c,58506d,7e56e9;music_disc_mellohi=i403744,1c1c1c,6b4f77,680792;music_disc_oth"
    "erside=i343c3a,1c1c1c,456058,39997b;music_disc_pigstep=i6e3629,411414,9e623b,eebe3d;music_disc_precipice=i696b"
    "62,41423a,93907e,ad9478;music_disc_relic=i6b4a43,45241d,867977,61bae7;music_disc_stal=i2e2e2e,131313,464646,46"
    "4646;music_disc_strad=i444444,1c1c1c,777777,777777;music_disc_wait=i373b40,1c1c1c,505b6a,6289c1;music_disc_war"
    "d=i343b32,1c1c1c,475c40,428c29;mutton=ib53f38,761712,e4756c,da362e;mycelium=b715747,513b2a,91705a,ac7c55;name_"
    "tag=ia59b7e,6a5b41,dfd1ab,ceac6d;nautilus_shell=ia38570,76543f,c6bbaa,b85f43;nether_brick=i3d1f25,2c151a,4c292"
    "f,4c292f;nether_brick_fence=b2c151a,1c0e11,3b1c22,3b1c22;nether_brick_slab=b2c151a,1c0e11,3b1c22,3b1c22;nether"
    "_brick_stairs=b2c151a,1c0e11,3b1c22,3b1c22;nether_brick_wall=b2c151a,1c0e11,3b1c22,3b1c22;nether_bricks=b2c151"
    "a,1c0e11,3b1c22,3b1c22;nether_gold_ore=b73362a,511b1b,9f5e37,e39e2d;nether_quartz_ore=b75413e,531c1c,a17b71,9d"
    "605b;nether_sprouts=i139785,167e86,13af85,14b485;nether_star=i99ad9d,597575,dde5bc,f0f286;nether_wart=i771c23,"
    "521217,ac2c37,a62530;nether_wart_block=b720202,5e0100,830606,971616;netherite_axe=i432f34,241214,604e52,62373a"
    ";netherite_block=b423d3f,322a2b,504c50,504c50;netherite_boots=i312b2d,181212,4f494d,4f494d;netherite_chestplat"
    "e=i393335,1d1718,595157,595157;netherite_helmet=i332e2f,1b1515,4f4a4e,4f4a4e;netherite_hoe=i402f33,1c1415,6a54"
    "58,6f413f;netherite_ingot=i3e393a,241d1e,595659,595659;netherite_leggings=i342e2f,171111,514c50,514c50;netheri"
    "te_pickaxe=i412d33,231012,6b565b,6c3f3d;netherite_scrap=i50322a,2e150e,6c5049,5d342c;netherite_shovel=i46343a,"
    "241213,706067,673c3f;netherite_sword=i45323b,251315,655860,512d3e;netherite_upgrade_smithing_template=i5c393b,"
    "421313,666c71,36b4c5;netherrack=b612626,4d1818,743434,7c3a3a;note_block=b583a28,30281d,87563c,945d41;oak_boat="
    "i7a633e,493924,b4945f,bc9862;oak_button=ba2824e,806538,bc9860,c29d62;oak_chest_boat=i735a32,392c1a,b38e54,a571"
    "23;oak_door=i8e7546,715b38,9e844e,987844;oak_fence=ba2824e,806538,bc9860,c29d62;oak_fence_gate=ba2824e,806538,"
    "bc9860,c29d62;oak_hanging_sign=i8b7147,594b36,b49259,bd9a5f;oak_leaves=b559c38,3b6d27,6abb47,559c38;oak_log=b9"
    "77949,6b5330,b5935c,b39258;oak_planks=ba2824e,806538,bc9860,c29d62;oak_pressure_plate=ba2824e,806538,bc9860,c2"
    "9d62;oak_sapling=b4d6a28,3d4617,4b9e37,57ad3f;oak_sign=i907343,634d2c,b29158,b6945a;oak_slab=ba2824e,806538,bc"
    "9860,c29d62;oak_stairs=ba2824e,806538,bc9860,c29d62;oak_trapdoor=b7c6338,534423,a27e4b,b08a50;oak_wood=b6d5532"
    ",4e3d24,87693e,917142;observer=b474545,302c2c,686767,473737;obsidian=b0f0a18,010003,221834,36244e;ocelot_spawn"
    "_egg=ibcbcbc,7c7c7c,e7e7e7,e7e7e7;ochre_froglight=bfaf5ce,f5e3a1,feffec,f2d88c;ominous_bottle=i434e5d,241828,5"
    "894a0,98557d;ominous_trial_key=i4a5950,2f332f,698d7b,927d74;orange_bed=bf07613,e76706,f88621,e36302;orange_can"
    "dle=ida6c13,ab4a08,fe942d,ff8118;orange_carpet=bf07613,e76706,f88621,e36302;orange_concrete=be06100,df6000,e16"
    "201,e16100;orange_concrete_powder=be3831f,dc7915,e9902b,e57f15;orange_dye=icc7e24,a5540e,e9a336,f4b33f;orange_"
    "glazed_terracotta=b9a935b,53846a,f99f45,ea6400;orange_shulker_box=bea6a08,d95d00,f4730f,ec6905;orange_stained_"
    "glass=bd87f33,d87f33,d87f33,d87f33;orange_stained_glass_pane=bd87f33,d87f33,d87f33,d87f33;orange_terracotta=ba"
    "15325,9f5123,a45627,a25224;orange_tulip=b5d8e1e,1a7d06,989f2b,f19d25;orange_wool=bf07613,e76706,f88621,e36302;"
    "oxeye_daisy=bb3ca8f,4c952c,edf2f2,f6b92a;oxidized_chiseled_copper=b53a184,407f6a,64bc99,59b292;oxidized_copper"
    "=b52a284,468770,5fb795,4fab90;oxidized_copper_bulb=b46846d,355c4d,5db695,50ab90;oxidized_copper_door=i4d9477,3"
    "f6b59,59b292,59b292;oxidized_copper_grate=b52a183,44826a,60b996,4fab90;oxidized_copper_trapdoor=b53a184,43806f"
    ",64bc99,4fab90;oxidized_cut_copper=b4f997e,3e7966,5fb492,5db594;oxidized_cut_copper_slab=b4f997e,3e7966,5fb492"
    ",5db594;oxidized_cut_copper_stairs=b4f997e,3e7966,5fb492,5db594;packed_ice=b8db4fa,7fa8f5,9cc0fe,7ca5f4;packed"
    "_mud=b8e6a4f,825f49,9a7657,9b7653;painting=i92836e,573a19,c4c1b8,78440f;panda_spawn_egg=ibcbcbc,7c7c7c,e7e7e7,"
    "e7e7e7;paper=id5d5d1,9b9b9b,fcfcf2,fcfcf2;parrot_spawn_egg=ibcbcbc,7c7c7c,e7e7e7,e7e7e7;pearlescent_froglight="
    "bf5f0ef,e5d8d9,fffefd,fffefd;peony=b817e8b,1d4122,e9bef9,de93f1;petrified_oak_slab=ba2824e,806538,bc9860,c29d6"
    "2;phantom_membrane=ia1918b,795f70,d1cbb3,d1cbb3;phantom_spawn_egg=ibcbcbc,7c7c7c,e7e7e7,e7e7e7;pig_spawn_egg=i"
    "bcbcbc,7c7c7c,e7e7e7,e7e7e7;piglin_banner_pattern=ic3bca9,8d7e5d,ebebeb,7a6546;piglin_brute_spawn_egg=ibcbcbc,"
    "7c7c7c,e7e7e7,e7e7e7;piglin_spawn_egg=ibcbcbc,7c7c7c,e7e7e7,e7e7e7;pillager_spawn_egg=ibcbcbc,7c7c7c,e7e7e7,e7"
    "e7e7;pink_bed=bed8dac,e37499,f4a6bf,da6992;pink_candle=id37094,a94c73,f79eb9,de6594;pink_carpet=bed8dac,e37499"
    ",f4a6bf,da6992;pink_concrete=bd5658e,d4648d,d6668f,d5648e;pink_concrete_powder=be499b5,dd88a8,ebacc3,de84a8;pi"
    "nk_dye=ic97fa9,8b3f74,f3b3d1,cb78a3;pink_glazed_terracotta=beb9ab5,e2779c,f4b5cb,d6658f;pink_petals=ie4b0bb,bd"
    "916e,f8cfe9,9fa635;pink_shulker_box=be6799d,d4648d,f28aa9,dc6a93;pink_stained_glass=bf27fa5,f27fa5,f27fa5,f27f"
    "a5;pink_stained_glass_pane=bf27fa5,f27fa5,f27fa5,f27fa5;pink_terracotta=ba14e4e,9f4b4c,a45050,a34d4d;pink_tuli"
    "p=b639d4e,1e7e09,bcbcbb,55ab2d;pink_wool=bed8dac,e37499,f4a6bf,da6992;piston=b616060,434242,808080,808080;pitc"
    "her_plant=i7a90bd,66559b,8dc5d4,a2cce2;pitcher_pod=i684333,40291f,97664e,ba774b;plenty_pottery_sherd=i67392f,4"
    "d2a22,84493c,965444;podzol=b7a5739,563c1f,a07451,b47f54;pointed_dripstone=i886d5d,775851,98826a,a08d71;poisono"
    "us_potato=i8c8236,4e5127,c9bb49,9e5b05;polar_bear_spawn_egg=ibcbcbc,7c7c7c,e7e7e7,e7e7e7;polished_andesite=b84"
    "8685,6f7272,989b99,989b99;polished_andesite_slab=b848685,6f7272,989b99,989b99;polished_andesite_stairs=b848685"
    ",6f7272,989b99,989b99;polished_basalt=b636264,49464d,7d7d7d,7d7d7d;polished_blackstone=b353038,272122,43404c,4"
    "3404c;polished_blackstone_brick_slab=b302a31,20171a,403d4a,403d4a;polished_blackstone_brick_stairs=b302a31,201"
    "71a,403d4a,403d4a;polished_blackstone_brick_wall=b302a31,20171a,403d4a,403d4a;polished_blackstone_bricks=b302a"
    "31,20171a,403d4a,403d4a;polished_blackstone_button=b353038,272122,43404c,43404c;polished_blackstone_pressure_p"
    "late=b353038,272122,43404c,43404c;polished_blackstone_slab=b353038,272122,43404c,43404c;polished_blackstone_st"
    "airs=b353038,272122,43404c,43404c;polished_blackstone_wall=b353038,272122,43404c,43404c;polished_deepslate=b48"
    "4849,313131,5d5d5d,5d5d5d;polished_deepslate_slab=b484849,313131,5d5d5d,5d5d5d;polished_deepslate_stairs=b4848"
    "49,313131,5d5d5d,5d5d5d;polished_deepslate_wall=b484849,313131,5d5d5d,5d5d5d;polished_diorite=bc0c1c2,9b9d9f,d"
    "fdcdf,dfdcdf;polished_diorite_slab=bc0c1c2,9b9d9f,dfdcdf,dfdcdf;polished_diorite_stairs=bc0c1c2,9b9d9f,dfdcdf,"
    "dfdcdf;polished_granite=b9a6a59,815747,ad7e6c,b6836e;polished_granite_slab=b9a6a59,815747,ad7e6c,b6836e;polish"
    "ed_granite_stairs=b9a6a59,815747,ad7e6c,b6836e;polished_tuff=b616863,545b54,70746e,70746e;polished_tuff_slab=b"
    "616863,545b54,70746e,70746e;polished_tuff_stairs=b616863,545b54,70746e,70746e;polished_tuff_wall=b616863,545b5"
    "4,70746e,70746e;popped_chorus_fruit=i7a517a,5c355c,996f99,8f648f;poppy=b804025,294822,c0492a,ed302c;porkchop=i"
    "d17171,833f3f,ffa4a4,ff7777;potato=ib28033,824602,e1b35c,9a5500;potion=ia3a3a3,727272,d6d6d6,d6d6d6;powder_sno"
    "w_bucket=i919fa1,424242,daeeee,76c6d4;powered_rail=b896d4a,53281c,bca870,e8b829;prismarine=b62a291,43856f,87bf"
    "b3,5ea496;prismarine_brick_slab=b63ab9e,4f927f,7cc1b7,5aafa4;prismarine_brick_stairs=b63ab9e,4f927f,7cc1b7,5aa"
    "fa4;prismarine_bricks=b63ab9e,4f927f,7cc1b7,5aafa4;prismarine_crystals=i8daea2,507067,cee2d5,91c5b7;prismarine"
    "_shard=i6ca392,3c7665,9ccab8,539882;prismarine_slab=b62a291,43856f,87bfb3,5ea496;prismarine_stairs=b62a291,438"
    "56f,87bfb3,5ea496;prismarine_wall=b62a291,43856f,87bfb3,5ea496;prize_pottery_sherd=i6a3b30,4e2a22,894c3e,9d574"
    "7;pufferfish=ibe9a52,83642b,f6ce7f,fcb00a;pufferfish_bucket=i8b8576,374566,cfc5a5,eca711;pufferfish_spawn_egg="
    "ibcbcbc,7c7c7c,e7e7e7,e7e7e7;pumpkin=bc67618,a65d0f,e39125,e38f18;pumpkin_pie=ic88c4d,93602e,efb76c,c46518;pum"
    "pkin_seeds=ic9c792,caba7c,c8d4aa,cab16e;purple_bed=b792aac,6b22a1,8933b9,9440c9;purple_candle=i6f23a3,521a83,8"
    "f2dc3,942aca;purple_carpet=b792aac,6b22a1,8933b9,9440c9;purple_concrete=b641f9c,631f9b,65209d,641f9c;purple_co"
    "ncrete_powder=b8337b1,7a32a9,8d3db9,8a3abb;purple_dye=i8541b0,522280,b065d2,8c39bc;purple_glazed_terracotta=b6"
    "d2f98,3e2855,953fcb,9a42d2;purple_shulker_box=b67209c,57198a,7325a8,7225a8;purple_stained_glass=b7f3fb2,7f3fb2"
    ",7f3fb2,7f3fb2;purple_stained_glass_pane=b7f3fb2,7f3fb2,7f3fb2,7f3fb2;purple_terracotta=b764656,734453,794858,"
    "794656;purple_wool=b792aac,6b22a1,8933b9,9440c9;purpur_block=ba97da9,986a97,ba94ba,a472a3;purpur_pillar=bab80a"
    "b,9b6d9a,bc99bc,a472a3;purpur_slab=ba97da9,986a97,ba94ba,a472a3;purpur_stairs=ba97da9,986a97,ba94ba,a472a3;qua"
    "rtz=ib9aca1,897870,e6e0d7,e6e0d7;quartz_block=bebe5de,e6dfd5,efebe8,efebe8;quartz_bricks=beae5dd,e3ddd2,efece9"
    ",efece9;quartz_pillar=bebe5de,e4dfd3,f1eeeb,f1eeeb;quartz_slab=bebe5de,e6dfd5,efebe8,efebe8;quartz_stairs=bebe"
    "5de,e6dfd5,efebe8,efebe8;rabbit=icfa190,986151,f9daca,b47864;rabbit_foot=ia38058,6d533b,d0a975,c79e67;rabbit_h"
    "ide=i916f49,5f462f,be9561,c79e67;rabbit_spawn_egg=ibcbcbc,7c7c7c,e7e7e7,e7e7e7;rabbit_stew=i7e4d1f,322307,d581"
    "3e,ee8612;rail=b7d6f58,634c2b,a19584,a17e49;raiser_armor_trim_smithing_template=i554b42,332220,797769,53b0b3;r"
    "avager_spawn_egg=ibcbcbc,7c7c7c,e7e7e7,e7e7e7;raw_copper=i896045,573e2d,c48969,e1734a;raw_copper_block=b9a694f"
    ",6f5a41,bf8467,da7d60;raw_gold=id19f30,925614,fbe66b,e29104;raw_gold_block=bdda92e,bb7b21,fade4d,eea41a;raw_ir"
    "on=i9a8570,4b4232,eecfba,d8af93;raw_iron_block=ba6876b,7b6242,d7b298,d8af93;recovery_compass=i364e4e,0e1613,67"
    "9396,1cb4c1;red_bed=ba02722,942220,ae2d25,b6322a;red_candle=i9f2926,751e21,c8382f,d2382e;red_carpet=ba02722,94"
    "2220,ae2d25,b6322a;red_concrete=b8e2020,8d2020,8f2121,8e2020;red_concrete_powder=ba83632,9f3230,b23b35,b73d37;"
    "red_dye=iaa363f,7d212d,df574f,d2443f;red_glazed_terracotta=bb53b35,9a2421,ce5950,c13830;red_mushroom=bd84b43,c"
    "d1519,c5b599,fe2a2a;red_mushroom_block=bc82e2d,c02523,d23d3b,cd2c2a;red_nether_brick_slab=b450709,300001,5f101"
    "3,711619;red_nether_brick_stairs=b450709,300001,5f1013,711619;red_nether_brick_wall=b450709,300001,5f1013,7116"
    "19;red_nether_bricks=b450709,300001,5f1013,711619;red_sand=bbe6621,b25f1d,ca6e24,cd7026;red_sandstone=bb9621c,"
    "a6530e,cb6f25,cb6e24;red_sandstone_slab=bb9621c,a6530e,cb6f25,cb6e24;red_sandstone_stairs=bb9621c,a6530e,cb6f2"
    "5,cb6e24;red_sandstone_wall=bba631d,a6520e,ce7128,ce7126;red_shulker_box=b8c1f1e,771717,9b2422,9c2522;red_stai"
    "ned_glass=b993333,993333,993333,993333;red_stained_glass_pane=b993333,993333,993333,993333;red_terracotta=b8f3"
    "d2e,8c3a2d,923f30,913d2f;red_tulip=b598020,326b09,5fa12e,ed302c;red_wool=ba02722,942220,ae2d25,b6322a;redstone"
    "=i6b0500,330200,bb0900,ff0000;redstone_block=baf1805,810f00,e02008,e62008;redstone_lamp=b5f361e,311a11,94572f,"
    "a76438;redstone_ore=b8c6d6d,8e4747,9b8585,e81e1e;redstone_torch=bab4f2c,53311f,cdaa59,ffb300;reinforced_deepsl"
    "ate=b4f524f,353535,70796f,728479;repeater=i7d5a4f,5b0203,aeb2aa,850404;repeating_command_block=b7f6da6,553b7b,"
    "b2abc4,6646bd;respawn_anchor=b200a3c,020105,471578,6e06c1;rib_armor_trim_smithing_template=i2f2a32,211216,354a"
    "59,1389a6;rooted_dirt=b90674c,6f4e35,b2856b,b9855c;rose_bush=b834225,443d1b,c5472d,ed302c;rotten_flesh=i7b3c1d"
    ",3e1f0c,b65b34,b44420;saddle=i8f4420,4d200c,d36c39,da662c;salmon=i6c4841,49322b,8b6b60,b33c3a;salmon_bucket=i7"
    "0727a,3a3735,b9b9b9,4258c3;salmon_spawn_egg=ibcbcbc,7c7c7c,e7e7e7,e7e7e7;sand=bdbcfa3,d5c395,e2dab0,d3c091;san"
    "dstone=bd7ca9a,ccb47f,e2dcb1,c6ae71;sandstone_slab=bd7ca9a,ccb47f,e2dcb1,c6ae71;sandstone_stairs=bd7ca9a,ccb47"
    "f,e2dcb1,c6ae71;sandstone_wall=bd8cb9b,cbb47e,e5dfb6,c6ae71;scaffolding=baa8349,87613f,caae54,cfb74f;scrape_po"
    "ttery_sherd=i6c3c31,4f2b23,8b4e3f,9f5949;sculk=b0d1b21,0d1217,0a2930,073a41;sculk_catalyst=b596d6d,1c3744,8199"
    "87,053640;sculk_sensor=b0d3d48,06262d,1a6375,1d7589;sculk_shrieker=b0d1b21,0d1217,0a2930,073a41;sculk_vein=b07"
    "313a,0e1a20,044d5b,066b76;sea_lantern=bacc8be,5d9184,e0eae1,599082;sea_pickle=i647038,414517,98b176,6c722a;sea"
    "grass=i337f08,246200,449418,389306;sentry_armor_trim_smithing_template=i4f5a5a,322e35,678884,3db2be;shaper_arm"
    "or_trim_smithing_template=i55483f,332220,737366,64a9a6;sheaf_pottery_sherd=i683a2f,4c2820,884c3e,9f5949;shears"
    "=i8d706a,603228,bdbdbd,9a493b;sheep_spawn_egg=ibcbcbc,7c7c7c,e7e7e7,e7e7e7;shelter_pottery_sherd=i6b3b31,4e2a2"
    "2,8a4d3f,9f5949;short_grass=b66b044,477b2f,80d455,66b044;shroomlight=bf09246,d95c08,fec886,e47205;shulker_box="
    "b8b608b,7b567b,976997,976697;shulker_shell=i704b75,492c57,9b6f9a,89598d;shulker_spawn_egg=ibcbcbc,7c7c7c,e7e7e"
    "7,e7e7e7;silence_armor_trim_smithing_template=i32484c,0f1e24,547d80,4ac4cd;silverfish_spawn_egg=ibcbcbc,7c7c7c"
    ",e7e7e7,e7e7e7;skeleton_horse_spawn_egg=ibcbcbc,7c7c7c,e7e7e7,e7e7e7;skeleton_spawn_egg=ibcbcbc,7c7c7c,e7e7e7,"
    "e7e7e7;skull_banner_pattern=ic3bca9,8d7e5d,ebebeb,7a6546;skull_pottery_sherd=i693a30,4c2820,8a4d3f,9f5949;slim"
    "e_ball=i639b5b,3e6739,89cf81,8cd782;slime_block=b6fc05b,63b54c,78c864,62b64a;slime_spawn_egg=ibcbcbc,7c7c7c,e7"
    "e7e7,e7e7e7;small_amethyst_bud=b8363c0,64479e,a783e7,b38ef3;small_dripleaf=b5e772d,465b2b,6f902d,70922d;smithi"
    "ng_table=b401c17,331816,4b1f1a,52221d;smoker=b6b6967,4f4944,858585,574a36;smooth_basalt=b48484e,333541,5c5b5c,"
    "5c5b5c;smooth_quartz=bece6df,eae2da,eeeae6,eeeae6;smooth_quartz_slab=bece6df,eae2da,eeeae6,eeeae6;smooth_quart"
    "z_stairs=bece6df,eae2da,eeeae6,eeeae6;smooth_red_sandstone=bb5611f,ad5c1b,bc6622,c06822;smooth_red_sandstone_s"
    "lab=bb5611f,ad5c1b,bc6622,c06822;smooth_red_sandstone_stairs=bb5611f,ad5c1b,bc6622,c06822;smooth_sandstone=bdf"
    "d6aa,dbcfa3,e3dbb1,dbcda0;smooth_sandstone_slab=bdfd6aa,dbcfa3,e3dbb1,dbcda0;smooth_sandstone_stairs=bdfd6aa,d"
    "bcfa3,e3dbb1,dbcda0;smooth_stone=b9e9e9e,898989,acacac,acacac;smooth_stone_slab=b9e9e9e,898989,acacac,acacac;s"
    "niffer_egg=i534b46,452a34,68715c,b44441;sniffer_spawn_egg=ibcbcbc,7c7c7c,e7e7e7,e7e7e7;snort_pottery_sherd=i67"
    "3a2f,4c2820,884c3e,9d5747;snout_armor_trim_smithing_template=i383d45,231d1e,4b636d,348f9d;snow=bf9fefe,f1fdfd,"
    "ffffff,ffffff;snow_block=bf9fefe,f1fdfd,ffffff,ffffff;snow_golem_spawn_egg=ibcbcbc,7c7c7c,e7e7e7,e7e7e7;snowba"
    "ll=ic6dede,95b8b8,f4fbfb,7ba6a6;soul_campfire=i5f8471,473822,8fcbbb,22c0c7;soul_lantern=i517f8c,3f4555,74e6ea,"
    "2ac9cf;soul_sand=b513e32,3d2e25,675042,675042;soul_soil=b4b392e,3a2c24,5f483b,5f483b;soul_torch=b6d7359,443622"
    ",96baa4,19c7cd;spawner=b242e3e,1c1d2b,324459,455673;spectral_arrow=ib89132,7b3f05,f8f376,dab930;spider_eye=i61"
    "1128,2c0011,9a3042,9d1e2d;spider_spawn_egg=ibcbcbc,7c7c7c,e7e7e7,e7e7e7;spire_armor_trim_smithing_template=i92"
    "709f,7b4e85,a992b7,29a3b5;splash_potion=ia3a3a3,727272,d6d6d6,d6d6d6;sponge=bc3c04a,b1a746,d4d54c,e1e351;spore"
    "_blossom=bce609e,924072,f87ec3,ea7494;spruce_boat=i5b4328,37291b,856033,946a38;spruce_button=b725430,5d4426,84"
    "6239,886539;spruce_chest_boat=i604623,302415,94692d,a57123;spruce_door=i665035,54442c,7b5e3d,7a5a36;spruce_fen"
    "ce=b725430,5d4426,846239,886539;spruce_fence_gate=b725430,5d4426,846239,886539;spruce_hanging_sign=i5e482d,382"
    "916,7d5f3a,866439;spruce_leaves=b4f9235,376625,63af42,4f9235;spruce_log=b6c502e,553d23,7f5f38,836139;spruce_pl"
    "anks=b725430,5d4426,846239,886539;spruce_pressure_plate=b725430,5d4426,846239,886539;spruce_sapling=b2c3c24,23"
    "2414,345334,432c14;spruce_sign=i5c4224,32210d,7c5c35,836239;spruce_slab=b725430,5d4426,846239,886539;spruce_st"
    "airs=b725430,5d4426,846239,886539;spruce_trapdoor=b674f2f,544026,7a5c3b,805e36;spruce_wood=b3a2510,2e1b09,472f"
    "16,4d3317;spyglass=i906f43,462e23,d3bd6e,de923a;squid_spawn_egg=ibcbcbc,7c7c7c,e7e7e7,e7e7e7;stick=i4b3815,281"
    "e0b,785a22,896727;sticky_piston=b616060,434242,808080,808080;stone=b7d7d7d,717171,888888,888888;stone_axe=i564"
    "e3e,271f11,858380,785a22;stone_brick_slab=b7a797a,636463,8f8d8f,8f8d8f;stone_brick_stairs=b7a797a,636463,8f8d8"
    "f,8f8d8f;stone_brick_wall=b7a797a,636463,8f8d8f,8f8d8f;stone_bricks=b7a797a,636463,8f8d8f,8f8d8f;stone_button="
    "b7d7d7d,717171,888888,888888;stone_hoe=i4d4432,1a1917,817357,896727;stone_pickaxe=i4e4535,1d1a13,837966,836225"
    ";stone_pressure_plate=b7d7d7d,717171,888888,888888;stone_shovel=i59503f,231c10,8e8c88,896727;stone_slab=b7d7d7"
    "d,717171,888888,888888;stone_stairs=b7d7d7d,717171,888888,888888;stone_sword=i575551,272521,928f8a,5a4726;ston"
    "ecutter=b767576,5b5b5b,878687,878687;stray_spawn_egg=ibcbcbc,7c7c7c,e7e7e7,e7e7e7;strider_spawn_egg=ibcbcbc,7c"
    "7c7c,e7e7e7,e7e7e7;string=i8f9a9b,2f4547,f1f1f1,f1f1f1;stripped_acacia_log=ba65b33,98522e,b66135,ba6337;stripp"
    "ed_acacia_wood=bae5c3b,a15938,ba603e,c1623f;stripped_bamboo_block=bb29e48,83722d,ddc663,d9c25e;stripped_birch_"
    "log=bbfab74,ad9763,d2be82,d7c185;stripped_birch_wood=bc4b076,b8a26c,cebc80,c4ac72;stripped_cherry_log=bdda49d,"
    "cd8581,e6bcb2,c97d79;stripped_cherry_wood=bd79194,d18889,db979d,cc837e;stripped_crimson_hyphae=b89395a,7e3451,"
    "963e62,9b4165;stripped_crimson_stem=b793852,663247,883d5b,8f3c5e;stripped_dark_oak_log=b412c16,362615,4d3117,4"
    "f3318;stripped_dark_oak_wood=b483824,413321,503d26,523f27;stripped_jungle_log=ba57a51,996f45,b0865d,aa7954;str"
    "ipped_jungle_wood=bab8454,9a7f48,ba8c60,ae8054;stripped_mangrove_log=b6d2b2b,622122,763632,722f2e;stripped_man"
    "grove_wood=b77362f,722f2f,7a3d2f,7b3e2f;stripped_oak_log=ba0814d,856b3c,b5935c,b39258;stripped_oak_wood=bb1905"
    "6,a1814b,be9c60,b89457;stripped_spruce_log=b69502e,4c3d22,7f5f38,836139;stripped_spruce_wood=b735934,65542f,80"
    "5f37,856138;stripped_warped_hyphae=b399693,308b86,41a19f,399e9a;stripped_warped_stem=b34807c,2d6a61,38918e,389"
    "892;structure_block=b584a5a,141215,b89ab8,b89ab8;structure_void=i18565d,0f484e,2b666b,125e64;sugar=ic5c5ce,7d7"
    "d90,fcfcfc,fcfcfc;sugar_cane=i559123,2d510f,80d237,97f544;sunflower=bf6c436,e89b26,fee649,f5ba27;suspicious_gr"
    "avel=b817d7c,6d6664,969393,969393;suspicious_sand=bd9cc9f,d1bc8b,e3dcb2,cbb47e;suspicious_stew=i69552f,2d1f06,"
    "afa164,a6ba5b;sweet_berries=i56231c,401112,683829,a50700;tadpole_bucket=i707774,323332,bcbcbc,4b6e5c;tadpole_s"
    "pawn_egg=ibcbcbc,7c7c7c,e7e7e7,e7e7e7;tall_grass=b68b445,497e30,82d857,68b445;target=be2aa9d,c63837,f3ebdf,d13"
    "333;terracotta=b985e43,955c43,995f45,9c5d41;tide_armor_trim_smithing_template=i59a79c,3d806f,70c9c2,4dcfd5;tin"
    "ted_glass=b2e2234,291c2f,35283b,35283b;tipped_arrow=iababab,4d4d4d,f2f2f2,f2f2f2;tnt=ba64235,9d2319,a17671,db2"
    "f1a;tnt_minecart=i6c4d45,212423,9e8989,db441a;torch=b8a713f,443622,dfbb5e,ffb300;torchflower=b64654d,1c4e39,ae"
    "9e50,e98b20;torchflower_seeds=i557545,185036,a49e50,7d9e58;totem_of_undying=ib38c4c,8c4714,e7d38d,78af57;trade"
    "r_llama_spawn_egg=ibcbcbc,7c7c7c,e7e7e7,e7e7e7;trial_key=i715142,422d24,af7d66,d57348;trial_spawner=b293b4c,1b"
    "2a38,37566a,406278;trident=i7a938c,225244,e3e3e3,549787;tripwire_hook=b8e8576,7b776f,a39279,b4905a;tropical_fi"
    "sh=ic96c3d,8f3d1a,f2a87d,e86213;tropical_fish_bucket=i8b7776,373742,ccc1bb,d56936;tropical_fish_spawn_egg=ibcb"
    "cbc,7c7c7c,e7e7e7,e7e7e7;tube_coral=b2f53c5,1d3a90,3e6ee4,314fdd;tube_coral_block=b3157ce,2243a9,3e71e4,314fdd"
    ";tube_coral_fan=b325bd0,2343ac,3d76e5,314fdd;tuff=b6c6d66,57584d,85847c,85847c;tuff_brick_slab=b62665f,474e44,"
    "7d7d74,7d7d74;tuff_brick_stairs=b62665f,474e44,7d7d74,7d7d74;tuff_brick_wall=b62665f,474e44,7d7d74,7d7d74;tuff"
    "_bricks=b62665f,474e44,7d7d74,7d7d74;tuff_slab=b6c6d66,57584d,85847c,85847c;tuff_stairs=b6c6d66,57584d,85847c,"
    "85847c;tuff_wall=b6c6d66,57584d,85847c,85847c;turtle_egg=ia3a988,4b513d,f4eac8,49aa91;turtle_helmet=i256f32,0a"
    "3219,44b547,47bf4a;turtle_scute=i359444,226e44,45bb48,47bf4a;turtle_spawn_egg=ibcbcbc,7c7c7c,e7e7e7,e7e7e7;twi"
    "sting_vines=b14877a,166663,12a785,14b485;vault=b2c2b38,251f2e,343741,343741;verdant_froglight=be5f4e4,c5e5c1,f"
    "8fdf8,a6d49f;vex_armor_trim_smithing_template=i4f6060,322e35,619796,3abacb;vex_spawn_egg=ibcbcbc,7c7c7c,e7e7e7"
    ",e7e7e7;villager_spawn_egg=ibcbcbc,7c7c7c,e7e7e7,e7e7e7;vindicator_spawn_egg=ibcbcbc,7c7c7c,e7e7e7,e7e7e7;vine"
    "=b4c8c38,356227,60a946,4c8c38;wandering_trader_spawn_egg=ibcbcbc,7c7c7c,e7e7e7,e7e7e7;ward_armor_trim_smithing"
    "_template=i41575b,333232,458790,188fad;warden_spawn_egg=ibcbcbc,7c7c7c,e7e7e7,e7e7e7;warped_button=b2b6863,1c4"
    "842,398786,3a8e8c;warped_door=i2f8782,2a655c,27a7a2,22b59e;warped_fence=b2b6863,1c4842,398786,3a8e8c;warped_fe"
    "nce_gate=b2b6863,1c4842,398786,3a8e8c;warped_fungus=b4a6d57,373c44,6b9859,ff6500;warped_fungus_on_a_stick=i515"
    "13b,362a14,7c805d,a68a3e;warped_hanging_sign=i2e6663,153e3b,3c8885,36998f;warped_hyphae=b393b4d,472334,20615b,"
    "127f68;warped_nylium=b483d3b,4a201f,2d6a65,139a85;warped_planks=b2b6863,1c4842,398786,3a8e8c;warped_pressure_p"
    "late=b2b6863,1c4842,398786,3a8e8c;warped_roots=b148a7c,166a69,12aa85,14b485;warped_sign=i2a6665,1c393e,378885,"
    "2f928c;warped_slab=b2b6863,1c4842,398786,3a8e8c;warped_stairs=b2b6863,1c4842,398786,3a8e8c;warped_stem=b356d6e"
    ",384149,378c89,268e8a;warped_trapdoor=b2f776f,255a51,37978f,369d91;warped_wart_block=b167779,186667,158785,139"
    "e85;water_bucket=i6f768a,353535,bcbcbc,2b57d3;waxed_chiseled_copper=bb86449,984f36,d4785d,db7d61;waxed_copper_"
    "block=bc06b4f,a4583e,d97c61,d67b5b;waxed_copper_bulb=b9c5639,693a1a,d0765a,dc7e63;waxed_copper_door=ib86a4e,8d"
    "533e,d67b5b,d67b5b;waxed_copper_grate=bbf6b4f,a3573d,d87c5f,d67b5b;waxed_copper_trapdoor=bbe6a4f,9c5239,de7f65"
    ",d67b5b;waxed_cut_copper=bbf6a50,a2563d,de7f66,d67b5b;waxed_cut_copper_slab=bbf6a50,a2563d,de7f66,d67b5b;waxed"
    "_cut_copper_stairs=bbf6a50,a2563d,de7f66,d67b5b;waxed_exposed_chiseled_copper=b9a7764,796856,b98676,ce8d83;wax"
    "ed_exposed_copper=ba17d67,89715b,b98778,ce8d83;waxed_exposed_copper_bulb=b876b59,5f5243,b68372,ce8d83;waxed_ex"
    "posed_copper_door=i967664,6f6251,ba8277,b37e6f;waxed_exposed_copper_grate=ba17d68,88715a,be877a,ce8d83;waxed_e"
    "xposed_copper_trapdoor=ba17d68,806f57,c5887e,ce8d83;waxed_exposed_cut_copper=b9a7965,7c6c55,b98777,ce8d83;waxe"
    "d_exposed_cut_copper_slab=b9a7965,7c6c55,b98777,ce8d83;waxed_exposed_cut_copper_stairs=b9a7965,7c6c55,b98777,c"
    "e8d83;waxed_oxidized_chiseled_copper=b53a184,407f6a,64bc99,59b292;waxed_oxidized_copper=b52a284,468770,5fb795,"
    "4fab90;waxed_oxidized_copper_bulb=b46846d,355c4d,5db695,50ab90;waxed_oxidized_copper_door=i4d9477,3f6b59,59b29"
    "2,59b292;waxed_oxidized_copper_grate=b52a183,44826a,60b996,4fab90;waxed_oxidized_copper_trapdoor=b53a184,43806"
    "f,64bc99,4fab90;waxed_oxidized_cut_copper=b4f997e,3e7966,5fb492,5db594;waxed_oxidized_cut_copper_slab=b4f997e,"
    "3e7966,5fb492,5db594;waxed_oxidized_cut_copper_stairs=b4f997e,3e7966,5fb492,5db594;waxed_weathered_chiseled_co"
    "pper=b68966f,5c7555,71b18a,66a977;waxed_weathered_copper=b6c996e,688557,6dad83,66a977;waxed_weathered_copper_b"
    "ulb=b5c7e63,485a50,6fa680,6faf87;waxed_weathered_copper_door=i6c8d62,646c48,73a378,66a977;waxed_weathered_copp"
    "er_grate=b6a986e,648257,6dad84,66a977;waxed_weathered_copper_trapdoor=b6c996e,687f55,72b18b,66a977;waxed_weath"
    "ered_cut_copper=b6d916b,617955,6caa82,67aa79;waxed_weathered_cut_copper_slab=b6d916b,617955,6caa82,67aa79;waxe"
    "d_weathered_cut_copper_stairs=b6d916b,617955,6caa82,67aa79;wayfinder_armor_trim_smithing_template=i564e45,3322"
    "20,768276,4cc6ce;weathered_chiseled_copper=b68966f,5c7555,71b18a,66a977;weathered_copper=b6c996e,688557,6dad83"
    ",66a977;weathered_copper_bulb=b5c7e63,485a50,6fa680,6faf87;weathered_copper_door=i6c8d62,646c48,73a378,66a977;"
    "weathered_copper_grate=b6a986e,648257,6dad84,66a977;weathered_copper_trapdoor=b6c996e,687f55,72b18b,66a977;wea"
    "thered_cut_copper=b6d916b,617955,6caa82,67aa79;weathered_cut_copper_slab=b6d916b,617955,6caa82,67aa79;weathere"
    "d_cut_copper_stairs=b6d916b,617955,6caa82,67aa79;weeping_vines=b84100c,600100,b82e24,df4a1f;wet_sponge=babb546"
    ",929b3d,c3c94a,cdce4a;wheat=i8c7a43,5d5537,bda558,d6b760;wheat_seeds=i3d861b,2e430c,61ba30,00e210;white_bed=be"
    "9ecec,d9dedf,f9fafa,f9fafa;white_candle=id1d9da,9dadb1,fcfcfc,82929e;white_carpet=be9ecec,d9dedf,f9fafa,f9fafa"
    ";white_concrete=bcfd5d6,ced4d5,d0d6d7,d0d6d7;white_concrete_powder=be1e3e3,d8dadb,ebecec,ebecec;white_dye=i999"
    "8ae,504e74,f1f1f2,59557f;white_glazed_terracotta=bbcd4ca,4899bf,f9fffe,fed83d;white_shulker_box=bd7dcdd,c3c9ca"
    ",e5e9e9,e5e9e9;white_stained_glass=bffffff,ffffff,ffffff,ffffff;white_stained_glass_pane=bffffff,ffffff,ffffff"
    ",ffffff;white_terracotta=bd1b2a1,d0af9f,d3b5a2,d1af9f;white_tulip=b5da447,288210,9dca97,55ab2d;white_wool=be9e"
    "cec,d9dedf,f9fafa,f9fafa;wild_armor_trim_smithing_template=i627669,474d3b,809d9b,3ab5c3;wind_charge=ibfc6da,9b"
    "a6b8,dce2fb,c5cfff;witch_spawn_egg=ibcbcbc,7c7c7c,e7e7e7,e7e7e7;wither_rose=b292c17,191910,3b3f20,38451a;withe"
    "r_skeleton_spawn_egg=ibcbcbc,7c7c7c,e7e7e7,e7e7e7;wither_spawn_egg=ibcbcbc,7c7c7c,e7e7e7,e7e7e7;wolf_armor=i8a"
    "5451,623234,ac736d,965954;wolf_spawn_egg=ibcbcbc,7c7c7c,e7e7e7,e7e7e7;wooden_axe=i4f3b16,271d0b,775a22,876626;"
    "wooden_hoe=i4a3715,21190a,775921,896726;wooden_pickaxe=i493614,221a0a,765821,886626;wooden_shovel=i523d17,251c"
    "0a,826225,896727;wooden_sword=i463414,231a0a,725520,866526;writable_book=i775d54,311104,c7c7c7,75321e;written_"
    "book=i5f3729,2d1003,927268,75321e;yellow_bed=bf8c527,f4b71b,fcd335,f2b217;yellow_candle=id2a938,9f7c25,fed751,"
    "ffda39;yellow_carpet=bf8c527,f4b71b,fcd335,f2b217;yellow_concrete=bf0af15,efae15,f2b016,f2b015;yellow_concrete"
    "_powder=be8c736,e3bd2d,eed242,ecc42d;yellow_dye=ib79e23,826517,e3d837,e7e72a;yellow_glazed_terracotta=beac058,"
    "c9912f,ffeda8,efab0e;yellow_shulker_box=bf8bc1d,f1b015,fcc623,f4b216;yellow_stained_glass=be5e533,e5e533,e5e53"
    "3,e5e533;yellow_stained_glass_pane=be5e533,e5e533,e5e533,e5e533;yellow_terracotta=bba8523,b88221,bc8725,bb8422"
    ";yellow_wool=bf8c527,f4b71b,fcd335,f2b217;zoglin_spawn_egg=ibcbcbc,7c7c7c,e7e7e7,e7e7e7;zombie_horse_spawn_egg"
    "=ibcbcbc,7c7c7c,e7e7e7,e7e7e7;zombie_spawn_egg=ibcbcbc,7c7c7c,e7e7e7,e7e7e7;zombie_villager_spawn_egg=ibcbcbc,"
    "7c7c7c,e7e7e7,e7e7e7;zombified_piglin_spawn_egg=ibcbcbc,7c7c7c,e7e7e7,e7e7e7"
)
# Our own 16x16 item pictures, drawn in code from a few measured colours per item, so the program never ships Mojang's pixels.
# Why: we wanted recognisable icons (Designer, Storage tab, Foreman tab) without bundling copyrighted textures.
# History: simple coloured shapes in the early versions; v7.7 added hand-drawn pictures for ingots, gems, dust, coal, tools, furnace,
# crafting table, hopper, glass, chest and for the ComputerCraft machines (see _special and _cc_tile).
# ============================================================ our own simplified item pictures
# Every vanilla item gets a 16x16 tile drawn here from four measured colours (average, dark, light, accent),
# so it looks like the real thing at a glance but contains none of Mojang's pixels.
import random as _random
import zlib as _zlib

_STATS = {}
EXTRA_STATS = {                      # items the game draws from a 3D model: colours picked by hand
    "chest": ("b", (160, 104, 45), (107, 68, 22), (197, 138, 69), (207, 207, 207)),
    "trapped_chest": ("b", (150, 98, 44), (101, 64, 22), (190, 132, 66), (186, 60, 50)),
    "ender_chest": ("b", (30, 60, 66), (14, 30, 36), (60, 120, 112), (96, 220, 180)),
    "torch": ("b", (139, 90, 43), (96, 60, 26), (255, 213, 74), (255, 213, 74)),
}


def icon_stats(name):
    """(kind, base, dark, light, accent) for a vanilla item id, or None for anything else (mods)."""
    if not _STATS:
        for part in ICON_DATA.split(";"):
            n, _, v = part.partition("=")
            k, rest = v[0], v[1:]
            cols = [tuple(int(c[i:i + 2], 16) for i in (0, 2, 4)) for c in rest.split(",")]
            _STATS[n] = (k, cols[0], cols[1], cols[2], cols[3])
    if not name.startswith("minecraft:"):
        return None
    short = name[10:]
    return _STATS.get(short) or EXTRA_STATS.get(short)


def icon_names():
    icon_stats("minecraft:stone")
    return sorted("minecraft:" + n for n in set(_STATS) | set(EXTRA_STATS))


def _mix(a, b, t):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


def _style(short, kind):
    if short.endswith("torch"):
        return "torch"
    if short == "chest" or short in ("trapped_chest", "ender_chest"):
        return "chest"
    if short.endswith("planks"):
        return "planks"
    if short.endswith("bricks") or short == "bricks" or short.endswith("_brick"):
        return "bricks"
    if short.endswith("_log") or short.endswith("_wood") or short.endswith("_stem") or short.endswith("_hyphae"):
        return "log"
    if "glass" in short and "bottle" not in short and "pane" not in short:
        return "glass"
    if "pane" in short:
        return "bars"
    if short.endswith("_ore") or short == "ancient_debris":
        return "ore"
    if short == "ladder":
        return "ladder"
    if short.endswith("_bars") or short == "iron_bars" or short == "chain":
        return "bars"
    if short.endswith("lantern") and short != "sea_lantern":
        return "lantern"
    if "leaves" in short:
        return "leaves"
    if kind == "i":
        return "gem"
    return "noise"


# ---- hand-drawn pictures for the things the colony is built from (ingots, gems, tools, ComputerCraft machines ...) ----
def _blank():
    return [[None] * 16 for _ in range(16)]


def _rect(g, x0, y0, x1, y1, c):
    for y in range(max(0, y0), min(15, y1) + 1):
        for x in range(max(0, x0), min(15, x1) + 1):
            g[y][x] = c


def _outline(g, amount=0.5):
    """Darken the outermost pixels so a shape stands out from the dark slot background."""
    edge = []
    for y in range(16):
        for x in range(16):
            if g[y][x] is None:
                continue
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                nx, ny = x + dx, y + dy
                if not (0 <= nx < 16 and 0 <= ny < 16) or g[ny][nx] is None:
                    edge.append((x, y))
                    break
    for x, y in edge:
        g[y][x] = _mix(g[y][x], (0, 0, 0), amount)
    return g


def _line(g, x0, y0, x1, y1, c, thick=1):
    n = max(abs(x1 - x0), abs(y1 - y0), 1)
    for i in range(n + 1):
        x = round(x0 + (x1 - x0) * i / n)
        y = round(y0 + (y1 - y0) * i / n)
        for dx in range(thick):
            for dy in range(thick):
                if 0 <= x + dx < 16 and 0 <= y + dy < 16:
                    g[y + dy][x + dx] = c


_TOOL = {"diamond": (77, 236, 222), "iron": (216, 216, 216), "golden": (250, 220, 60), "stone": (140, 140, 140),
         "wooden": (150, 110, 60), "netherite": (70, 60, 66)}
_INGOT = {"iron_ingot": (216, 216, 216), "gold_ingot": (250, 214, 56), "copper_ingot": (210, 120, 80), "netherite_ingot": (74, 62, 68),
          "brick": (170, 80, 60), "nether_brick": (70, 30, 36)}
_GEM = {"diamond": (80, 232, 220), "emerald": (40, 200, 90), "lapis_lazuli": (40, 70, 190), "quartz": (235, 230, 220),
        "amethyst_shard": (170, 110, 220), "echo_shard": (30, 90, 110)}
_DUST = {"redstone": (200, 20, 20), "glowstone_dust": (240, 200, 80), "gunpowder": (90, 90, 90), "sugar": (245, 245, 245),
         "bone_meal": (240, 240, 230), "blaze_powder": (250, 170, 30)}
_LUMP = {"coal": (40, 40, 44), "charcoal": (62, 50, 44), "raw_iron": (210, 160, 130), "raw_gold": (240, 200, 60), "raw_copper": (190, 110, 70)}


# v7.7: hand-drawn pictures. Each branch draws shapes with _rect/_line, then _outline darkens the edge so it stands out on the dark slot background.
def _special(name):
    ns, _, short = name.partition(":")
    if ns == "computercraft":
        return _cc_tile(short)
    if ns != "minecraft":
        return None
    g = _blank()
    rng = _random.Random(_zlib.crc32(name.encode()))
    if short in _INGOT:                                   # a bar seen from slightly above
        b = _INGOT[short]
        lt, dk = _mix(b, (255, 255, 255), 0.45), _mix(b, (0, 0, 0), 0.4)
        for y, x0 in ((5, 5), (6, 4), (7, 3)):
            _rect(g, x0, y, x0 + 9, y, lt)
        _rect(g, 3, 8, 12, 12, b)
        _rect(g, 3, 12, 12, 12, dk)
        _rect(g, 13, 5, 13, 9, dk)
        _rect(g, 12, 8, 12, 12, _mix(b, dk, 0.5))
        return _outline(g)
    if short in _GEM:                                     # a cut stone: crown on top, point below
        b = _GEM[short]
        lt, dk = _mix(b, (255, 255, 255), 0.55), _mix(b, (0, 0, 0), 0.35)
        for y in range(2, 14):
            half = 3 + (y - 2) * 0.8 if y < 7 else max(0, 8.2 - (y - 7) * 1.5)
            for x in range(16):
                if abs(x - 7.5) <= half:
                    g[y][x] = b if x >= 8 else lt
        for x in range(16):
            if g[7][x] is not None:
                g[7][x] = dk
        for y in range(8, 13):
            if g[y][8] is not None:
                g[y][8] = dk
        g[4][6] = g[3][7] = (255, 255, 255)
        return _outline(g)
    if short in _DUST:                                    # a little heap of powder
        b = _DUST[short]
        for y in range(6, 14):
            half = 1 + (y - 6) * 0.85
            for x in range(16):
                if abs(x - 7.5) <= half:
                    g[y][x] = _mix(b, (255, 255, 255) if rng.random() < 0.3 else (0, 0, 0), 0.25 if rng.random() < 0.7 else 0.0)
        return _outline(g, 0.4)
    if short in _LUMP or short.startswith("raw_"):       # a rough lump
        b = _LUMP.get(short, (150, 150, 150))
        for y in range(16):
            for x in range(16):
                d = ((x - 7.5) ** 2 + (y - 8.5) ** 2) ** 0.5
                if d < 5.2 + rng.random() * 1.4:
                    g[y][x] = _mix(b, (255, 255, 255), 0.32) if (x + y) % 5 == 0 and x < 8 else (_mix(b, (0, 0, 0), 0.25) if x > 9 and y > 9 else b)
        return _outline(g, 0.55)
    if short == "stick":
        _line(g, 3, 13, 12, 4, (150, 106, 54), 2)
        _line(g, 4, 13, 13, 4, (96, 64, 28))
        return _outline(g)
    if short == "paper":
        _rect(g, 3, 2, 12, 13, (240, 240, 235))
        for y in (5, 7, 9, 11):
            _rect(g, 5, y, 10, y, (150, 150, 150))
        _rect(g, 11, 2, 12, 3, (190, 190, 185))
        return _outline(g, 0.45)
    if short == "sugar_cane":
        for x, top in ((3, 4), (7, 1), (11, 3)):
            for y in range(top, 15):
                g[y][x] = (136, 200, 90) if (y - top) % 5 else (86, 150, 52)
                g[y][x + 1] = (96, 160, 60)
        return _outline(g, 0.4)
    if short.endswith("sapling") or short == "bamboo":
        _rect(g, 7, 8, 8, 14, (120, 84, 40))
        for cx, cy in ((4, 6), (10, 6), (7, 3), (7, 7)):
            _rect(g, cx - 2, cy - 2, cx + 2, cy + 1, (70, 150, 50))
            _rect(g, cx - 1, cy - 1, cx + 1, cy, (110, 190, 70))
        return _outline(g, 0.45)
    if short.endswith("_pickaxe"):
        mat = _TOOL.get(short[:-8], (180, 180, 180))
        _line(g, 3, 14, 11, 6, (140, 98, 48), 2)
        hd, hl = _mix(mat, (0, 0, 0), 0.3), _mix(mat, (255, 255, 255), 0.4)
        for (x, y) in ((4, 5), (5, 3), (7, 2), (9, 2), (11, 3), (12, 5), (13, 7)):
            _rect(g, x, y, x + 1, y + 1, mat)
        for (x, y) in ((5, 4), (8, 3), (10, 3), (12, 6)):
            g[y][x] = hl
        g[7][13] = g[8][13] = hd
        return _outline(g)
    if short == "furnace" or short == "blast_furnace":
        for y in range(16):
            for x in range(16):
                g[y][x] = _mix((130, 130, 130), (80, 80, 80) if rng.random() < 0.4 else (170, 170, 170), 0.5)
        _rect(g, 4, 7, 11, 13, (36, 36, 38))
        _rect(g, 5, 11, 10, 13, (230, 120, 30))
        _rect(g, 6, 12, 9, 13, (255, 210, 80))
        _rect(g, 0, 0, 15, 0, (170, 170, 170))
        return _outline(g, 0.4)
    if short == "crafting_table":
        for y in range(16):
            for x in range(16):
                g[y][x] = (150, 106, 56) if (x // 2 + y // 3) % 2 else (136, 94, 48)
        _rect(g, 0, 0, 15, 1, (96, 62, 30))
        _rect(g, 2, 3, 13, 8, (190, 150, 90))
        for k in (6, 9):
            _rect(g, k, 3, k, 8, (96, 62, 30))
        for k in (5, 7):
            _rect(g, 2, k, 13, k, (96, 62, 30))
        _rect(g, 3, 10, 5, 14, (110, 110, 110))
        _rect(g, 9, 11, 13, 13, (190, 190, 190))
        return _outline(g, 0.4)
    if short == "hopper":
        _rect(g, 1, 2, 14, 4, (70, 70, 74))
        _rect(g, 2, 3, 13, 3, (36, 36, 40))
        _rect(g, 2, 5, 13, 7, (96, 96, 100))
        _rect(g, 4, 8, 11, 9, (80, 80, 84))
        _rect(g, 6, 10, 9, 14, (70, 70, 74))
        _rect(g, 7, 11, 8, 14, (36, 36, 40))
        return _outline(g, 0.45)
    if short == "cobblestone":
        for y in range(16):
            for x in range(16):
                g[y][x] = (125, 125, 125)
        for by in range(0, 16, 5):
            off = rng.randrange(0, 5)
            for bx in range(-off, 16, 6):
                tone = _mix((125, 125, 125), (170, 170, 170) if rng.random() < 0.5 else (90, 90, 90), 0.4)
                _rect(g, bx + 1, by + 1, bx + 4, by + 3, tone)
        for y in range(16):
            for x in range(16):
                if g[y][x] == (125, 125, 125):
                    g[y][x] = (70, 70, 70)
                elif rng.random() < 0.3:
                    g[y][x] = _mix(g[y][x], (255, 255, 255) if rng.random() < 0.5 else (0, 0, 0), 0.12)
        return g
    if short == "stone":
        for y in range(16):
            for x in range(16):
                g[y][x] = _mix((125, 125, 125), (150, 150, 150) if rng.random() < 0.5 else (104, 104, 104), 0.5)
        return g
    if short in ("glass_pane", "glass"):                  # panes: a thin frame with a cross
        for y in range(16):
            for x in range(16):
                edge = x in (0, 15) or y in (0, 15)
                g[y][x] = (225, 245, 250) if edge else (170, 210, 225) if short == "glass_pane" else (190, 225, 235)
        if short == "glass_pane":
            _rect(g, 7, 0, 8, 15, (225, 245, 250))
            _rect(g, 0, 7, 15, 8, (225, 245, 250))
        for k in range(3, 6):
            g[k][k] = (255, 255, 255)
        return g
    if short == "chest":
        _rect(g, 1, 3, 14, 14, (160, 104, 45))
        _rect(g, 1, 3, 14, 7, (178, 122, 58))
        _rect(g, 1, 7, 14, 7, (96, 60, 22))
        _rect(g, 1, 11, 14, 11, (140, 90, 38))
        _rect(g, 7, 6, 8, 9, (225, 225, 225))
        return _outline(g, 0.45)
    return None


def _cc_tile(short):
    """ComputerCraft machines: grey casings, each with its own face."""
    g = _blank()
    case, rim, dark = (176, 176, 176), (210, 210, 210), (88, 88, 92)
    if short in ("computer_normal", "computer_advanced", "computer_command", "turtle_normal", "turtle_advanced"):
        gold = short.endswith("advanced")
        body = (230, 190, 60) if gold else case
        _rect(g, 1, 1, 14, 14, body)
        _rect(g, 1, 1, 14, 1, _mix(body, (255, 255, 255), 0.4))
        _rect(g, 1, 14, 14, 14, _mix(body, (0, 0, 0), 0.35))
        if short.startswith("computer"):                  # a screen with a prompt
            _rect(g, 3, 3, 12, 9, (20, 24, 40))
            _rect(g, 4, 5, 5, 5, (110, 255, 140)); _rect(g, 5, 6, 5, 6, (110, 255, 140)); _rect(g, 4, 7, 5, 7, (110, 255, 140))
            _rect(g, 7, 7, 9, 7, (110, 255, 140))
            _rect(g, 4, 11, 11, 12, _mix(body, (0, 0, 0), 0.2))
        else:                                             # a turtle: a face and a green shell
            _rect(g, 3, 3, 12, 8, (36, 40, 52))
            _rect(g, 4, 4, 5, 6, (255, 255, 255)); _rect(g, 10, 4, 11, 6, (255, 255, 255))
            _rect(g, 5, 5, 5, 6, (0, 0, 0)); _rect(g, 11, 5, 11, 6, (0, 0, 0))
            _rect(g, 6, 8, 9, 8, (255, 255, 255))
            _rect(g, 3, 10, 12, 13, (60, 160, 80))
            _rect(g, 4, 11, 6, 12, (90, 200, 110)); _rect(g, 9, 11, 11, 12, (90, 200, 110))
        return _outline(g, 0.5)
    if short == "disk_drive":
        _rect(g, 1, 2, 14, 13, case)
        _rect(g, 1, 2, 14, 2, rim)
        _rect(g, 3, 5, 12, 7, (30, 30, 34))                  # the slot
        _rect(g, 4, 6, 11, 6, (70, 70, 76))
        _rect(g, 11, 10, 12, 11, (80, 220, 90))              # the light
        _rect(g, 3, 10, 6, 11, dark)
        return _outline(g, 0.5)
    if short == "disk":                                   # a floppy disk
        _rect(g, 2, 1, 13, 14, (60, 110, 200))
        _rect(g, 5, 1, 10, 5, (200, 200, 205))               # the metal shutter
        _rect(g, 8, 2, 9, 4, (90, 90, 96))
        _rect(g, 4, 8, 11, 13, (240, 240, 235))              # the label
        for y in (10, 12):
            _rect(g, 5, y, 10, y, (150, 150, 150))
        return _outline(g, 0.5)
    rng = _random.Random(_zlib.crc32(short.encode()))
    _rect(g, 1, 1, 14, 14, case)                          # any other ComputerCraft part: a grey casing with its own coloured mark
    _rect(g, 1, 1, 14, 1, rim)
    mark = tuple(60 + rng.randrange(170) for _ in range(3))
    _rect(g, 5, 5, 10, 10, mark)
    _rect(g, 6, 6, 9, 9, _mix(mark, (255, 255, 255), 0.35))
    return _outline(g, 0.5)


def item_tile(name):
    """16 rows of 16 (r, g, b) tuples (None = see-through) for a vanilla item, or None for modded ones."""
    sp = _special(name)
    if sp is not None:
        return sp
    st = icon_stats(name)
    if st is None:
        return None
    kind, base, dark, light, acc = st
    short = name[10:]
    rng = _random.Random(_zlib.crc32(name.encode()))
    style = _style(short, kind)
    g = [[base] * 16 for _ in range(16)]

    def speckle(x0, y0, x1, y1, lo=0.17, hi=0.83, cell=2):
        for cy in range(y0, y1, cell):
            for cx in range(x0, x1, cell):
                r = rng.random()
                c = dark if r < lo else (light if r > hi else None)
                if c is None:
                    continue
                for yy in range(cy, min(cy + cell, y1)):
                    for xx in range(cx, min(cx + cell, x1)):
                        g[yy][xx] = _mix(base, c, 0.75)
        for yy in range(y0, y1):                       # a little per-pixel jitter
            for xx in range(x0, x1):
                if rng.random() < 0.12:
                    g[yy][xx] = _mix(g[yy][xx], dark if rng.random() < 0.5 else light, 0.35)

    if style == "noise":
        speckle(0, 0, 16, 16)
    elif style == "ore":
        speckle(0, 0, 16, 16, 0.2, 0.8, 2)
        for _ in range(6):
            sx, sy = rng.randrange(1, 14), rng.randrange(1, 14)
            for dx, dy in ((0, 0), (1, 0), (0, 1)):
                g[sy + dy][sx + dx] = acc
    elif style == "planks":
        for row in range(4):
            y0 = row * 4
            tone = _mix(base, light if row % 2 else dark, 0.18)
            for y in range(y0, y0 + 4):
                for x in range(16):
                    g[y][x] = tone
            for x in range(16):
                g[y0 + 3][x] = _mix(base, dark, 0.7)
            seam = (row * 5 + 3) % 14 + 1
            for y in range(y0, y0 + 3):
                g[y][seam] = _mix(base, dark, 0.55)
            for _ in range(3):
                g[y0 + rng.randrange(3)][rng.randrange(16)] = _mix(tone, dark, 0.3)
    elif style == "bricks":
        mortar = dark if ("stone" in short or "deepslate" in short or "nether" in short) else _mix(light, (215, 210, 200), 0.65)
        for y in range(16):
            for x in range(16):
                g[y][x] = base
        speckle(0, 0, 16, 16, 0.12, 0.88, 2)
        for y in range(16):
            for x in range(16):
                if y % 4 == 3:
                    g[y][x] = mortar
                else:
                    off = 4 if (y // 4) % 2 else 0
                    if (x + off) % 8 == 7:
                        g[y][x] = mortar
    elif style == "log":
        x = 0
        while x < 16:
            w = rng.choice((1, 2, 2, 3))
            c = rng.choice((dark, base, base, light))
            for xx in range(x, min(16, x + w)):
                for y in range(16):
                    g[y][xx] = _mix(base, c, 0.55)
            x += w
        for _ in range(10):
            g[rng.randrange(16)][rng.randrange(16)] = dark
    elif style == "glass":
        inner = _mix(base, (22, 28, 34), 0.55)
        for y in range(16):
            for x in range(16):
                edge = x in (0, 15) or y in (0, 15)
                g[y][x] = _mix(light, (255, 255, 255), 0.3) if edge else inner
        for k in range(3, 8):
            g[k][k] = (255, 255, 255)
        g[10][4] = g[4][10] = _mix(light, (255, 255, 255), 0.6)
    elif style == "chest":
        for y in range(16):
            for x in range(16):
                g[y][x] = _mix(base, light if y % 5 == 0 else dark, 0.22)
        for i in range(16):
            for (yy, xx) in ((0, i), (15, i), (i, 0), (i, 15)):
                g[yy][xx] = dark
            g[6][i] = dark
        for yy in (6, 7, 8):
            for xx in (7, 8):
                g[yy][xx] = acc
    elif style == "ladder":
        g = [[None] * 16 for _ in range(16)]
        for y in range(16):
            for x in (2, 3, 12, 13):
                g[y][x] = _mix(base, dark, 0.35)
        for y in (2, 3, 7, 8, 12, 13):
            for x in range(4, 12):
                g[y][x] = base
    elif style == "bars":
        g = [[None] * 16 for _ in range(16)]
        for y in range(16):
            for x in (5, 10):
                g[y][x] = light
                g[y][x + 1 if x + 1 < 16 else x] = _mix(base, dark, 0.4)
        for x in range(16):
            for y in (2, 13):
                g[y][x] = _mix(base, dark, 0.3)
    elif style == "lantern":
        g = [[None] * 16 for _ in range(16)]
        for y in range(3, 14):
            for x in range(4, 12):
                g[y][x] = acc if 5 <= y <= 11 and 5 <= x <= 10 else dark
        for x in range(6, 10):
            g[2][x] = dark
            g[1][x] = dark
        g[0][7] = g[0][8] = dark
    elif style == "torch":
        g = [[None] * 16 for _ in range(16)]
        for y in range(6, 16):
            g[y][7] = base
            g[y][8] = _mix(base, dark, 0.5)
        for (x, y) in ((7, 3), (8, 3), (7, 4), (8, 4), (6, 4), (9, 4), (7, 5), (8, 5), (6, 5), (9, 5)):
            g[y][x] = acc
        g[2][7] = g[2][8] = _mix(acc, (255, 255, 255), 0.6)
        g[3][7] = g[3][8] = _mix(acc, (255, 255, 255), 0.35)
    elif style == "leaves":
        speckle(0, 0, 16, 16, 0.3, 0.7, 2)
        for _ in range(14):
            g[rng.randrange(16)][rng.randrange(16)] = None
    else:                                                # gem: an item that isn't a block
        g = [[None] * 16 for _ in range(16)]
        for y in range(16):
            for x in range(16):
                d = ((x - 7.5) ** 2 + (y - 7.5) ** 2) ** 0.5
                if d <= 6.2:
                    shade = (x + y - 15) / 18.0
                    c = _mix(base, light if shade < 0 else dark, min(0.6, abs(shade)))
                    g[y][x] = dark if d > 5.3 else c
        g[4][5] = g[4][6] = g[5][5] = _mix(light, (255, 255, 255), 0.6)
        if acc != base:
            g[8][8] = g[8][9] = g[9][8] = acc
    return g


def tile_hex(name):
    """The tile as 16 rows of 16 'rrggbb' strings ('-' = see-through), for the 3D page; None for modded items."""
    t = display_tile(name)
    if t is None:
        return None
    return [["-" if c is None else "%02x%02x%02x" % c for c in row] for row in t]
# Importing the player's own textures (resource packs, the game jar, mods). They are read on the player's computer and kept in
# the settings folder; nothing is uploaded. Why: the player may want the real look, but we must not redistribute it.
# ============================================================ your own textures (resource packs, game jar, mods)
# Textures you import stay on your computer (in the settings folder); nothing is uploaded anywhere.
TEX = {"mode": "builtin", "tiles": {}, "sources": []}      # mode: builtin | imported


def texpack_file():
    return os.path.join(CONFIG_DIR, "textures.json.gz")


_TEX_NAME = re.compile(r"assets/([a-z0-9_.\-]+)/textures/(block|blocks|item|items)/([a-z0-9_.\-]+)\.png")
_SUFFIXES = ("", "_side", "_front", "_top")
_GREEN = {"leaves": (0.30, 0.55, 0.20), "grass": (0.36, 0.62, 0.24), "fern": (0.30, 0.55, 0.22),
          "vine": (0.30, 0.55, 0.22), "lily_pad": (0.18, 0.45, 0.20)}


def _pack_encode(rows):
    return "".join("------" if c is None else "%02x%02x%02x" % c for row in rows for c in row)


def _pack_decode(s):
    out = []
    for y in range(16):
        row = []
        for x in range(16):
            h = s[(y * 16 + x) * 6:(y * 16 + x) * 6 + 6]
            row.append(None if h == "------" else (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)))
        out.append(row)
    return out


def load_texpack():
    TEX["tiles"], TEX["sources"] = {}, []
    try:
        with gzip.open(texpack_file(), "rt", encoding="utf-8") as f:
            data = json.load(f)
        tiles = data.get("tiles", {})
        if isinstance(tiles, dict):
            TEX["tiles"] = {k: v for k, v in tiles.items() if isinstance(k, str) and isinstance(v, str) and len(v) == 1536}
            TEX["sources"] = [str(s) for s in data.get("sources", [])][:50]
    except Exception:
        pass


def save_texpack():
    try:
        os.makedirs(CONFIG_DIR, exist_ok=True)
        with gzip.open(texpack_file(), "wt", encoding="utf-8") as f:
            json.dump({"sources": TEX["sources"], "tiles": TEX["tiles"]}, f, separators=(",", ":"))
    except OSError:
        pass


def clear_texpack():
    TEX["tiles"], TEX["sources"], TEX["mode"] = {}, [], "builtin"
    try:
        os.remove(texpack_file())
    except OSError:
        pass


def pack_tile(name):
    """The imported texture for an item id (vanilla or modded), or None."""
    tiles = TEX["tiles"]
    if not tiles:
        return None
    ns, _, short = name.partition(":")
    for suf in _SUFFIXES:
        s = tiles.get("%s:%s%s" % (ns, short, suf))
        if s:
            return _pack_decode(s)
    return None


def display_tile(name):
    """What to draw for an item: your imported texture when that mode is on, else our simplified tile."""
    if TEX["mode"] == "imported":
        t = pack_tile(name)
        if t is not None:
            return t
    return item_tile(name)


def display_color(name):
    """Flat colour of an item: the average of what is drawn, else the measured / hash colour."""
    t = display_tile(name) if TEX["mode"] == "imported" and pack_tile(name) is not None else None
    if t is None:
        return item_color(name)
    px = [c for row in t for c in row if c]
    if not px:
        return item_color(name)
    return "#%02x%02x%02x" % tuple(sum(c[i] for c in px) // len(px) for i in range(3))


def _greenify(short, rows):
    for word, tint in _GREEN.items():
        if word in short:
            px = [c for row in rows for c in row if c]
            if px and max(max(c) - min(c) for c in px) < 30:         # grey texture the game would tint
                return [[None if c is None else tuple(min(255, int(tint[i] * 255 * (0.55 + sum(c) / 765.0))) for i in range(3))
                         for c in row] for row in rows]
    return rows


def import_texture_file(root, path, limit=8000):
    """Read every block/item texture from a resource pack (.zip), the game's version .jar, or a mod .jar.
    Returns how many textures were added. Raises ValueError for files that are not zip archives."""
    try:
        z = zipfile.ZipFile(path)
    except (zipfile.BadZipFile, OSError):
        raise ValueError("That isn't a resource pack or jar file (a zip archive).")
    found = {}
    with z:
        entries = []
        for info in z.infolist():
            m = _TEX_NAME.fullmatch(info.filename)
            if m and info.file_size < 3_000_000:
                entries.append((0 if m.group(2).startswith("block") else 1, m.group(1), m.group(3), info))
        entries.sort(key=lambda e: e[0])                    # item textures win over block ones of the same name
        for _kind, ns, short, info in entries[:limit]:
            try:
                img = tk.PhotoImage(master=root, data=base64.b64encode(z.read(info)).decode("ascii"))
            except Exception:
                continue
            w, h = img.width(), img.height()
            side = min(w, h)                                # tall strips are animations: use the first frame
            if side < 1:
                continue
            rows = []
            for ty in range(16):
                row = []
                for tx in range(16):
                    sx, sy = min(w - 1, int((tx + 0.5) * side / 16)), min(h - 1, int((ty + 0.5) * side / 16))
                    if img.transparency_get(sx, sy):
                        row.append(None)
                    else:
                        v = img.get(sx, sy)
                        if isinstance(v, str):
                            v = v.split()
                        row.append((int(v[0]), int(v[1]), int(v[2])))
                rows.append(row)
            if all(c is None for row in rows for c in row):
                continue
            found["%s:%s" % (ns, short)] = _pack_encode(_greenify(short, rows))
    if not found:
        raise ValueError("No textures found. A resource pack has  assets/minecraft/textures/block  inside it.")
    TEX["tiles"].update(found)
    label = os.path.basename(path)
    if label not in TEX["sources"]:
        TEX["sources"].append(label)
    TEX["mode"] = "imported"
    save_texpack()
    return len(found)


def pack_names():
    return sorted(k for k in TEX["tiles"] if not k.endswith(("_side", "_front", "_top")) or k.split(":")[0] != "minecraft")
# The shape generators (box, cylinder, sphere ...) and ready-made templates that fill the design grid.
# ---------------------------------------------------------------------------- shapes and templates
SHAPES = [
    ("box", "Box / room"),
    ("cylinder", "Cylinder (round shaft)"),
    ("sphere", "Sphere / ball cave"),
    ("dome", "Dome (half sphere)"),
    ("pyramid", "Pyramid"),
    ("stairs", "Staircase going up"),
]


def _solid_shape(kind, w, d, h):
    """All cells of the plain solid shape that fits the w x d x h box."""
    out = set()
    cx, cz = (w + 1) / 2.0, (d + 1) / 2.0
    rx, rz = w / 2.0, d / 2.0
    if kind == "box":
        return {(x, y, z) for y in range(1, h + 1) for z in range(1, d + 1) for x in range(1, w + 1)}
    if kind == "cylinder":
        for y in range(1, h + 1):
            for z in range(1, d + 1):
                for x in range(1, w + 1):
                    if ((x - cx) / rx) ** 2 + ((z - cz) / rz) ** 2 <= 1.0:
                        out.add((x, y, z))
        return out
    if kind in ("sphere", "dome"):
        ry = h / 2.0 if kind == "sphere" else float(h)
        cy = (h + 1) / 2.0 if kind == "sphere" else 0.5
        for y in range(1, h + 1):
            for z in range(1, d + 1):
                for x in range(1, w + 1):
                    if ((x - cx) / rx) ** 2 + ((z - cz) / rz) ** 2 + ((y - cy) / ry) ** 2 <= 1.0:
                        out.add((x, y, z))
        return out
    if kind == "pyramid":
        for y in range(1, h + 1):
            f = 1.0 - (y - 1) / float(h)
            hx, hz = rx * f, rz * f
            for z in range(1, d + 1):
                for x in range(1, w + 1):
                    if abs(x - cx) <= hx and abs(z - cz) <= hz - 0.01:
                        out.add((x, y, z))
        return out
    if kind == "stairs":
        lo, hi = max(1, int(cx - 1)), min(w, int(cx + 1.5))
        steps = min(h - 1, d)
        for k in range(steps):
            for x in range(lo, hi + 1):
                out.add((x, k + 1, k + 1))
                out.add((x, k + 2, k + 1))
        return out
    raise ValueError(kind)


def shape_cells(kind, w, d, h, hollow=False, caps=True):
    """Cells to dig for a shape. hollow = only the outer skin (walls); caps = floor and ceiling too."""
    solid = _solid_shape(kind, w, d, h)
    if not hollow or kind == "stairs":
        return solid
    if kind == "box":
        side = ((1, 0, 0), (-1, 0, 0), (0, 0, 1), (0, 0, -1))
        ends = ((0, 1, 0), (0, -1, 0))
    else:                          # curved skins need the diagonal neighbours too, or they fall apart
        side = tuple((a, 0, c) for a in (-1, 0, 1) for c in (-1, 0, 1) if (a, c) != (0, 0))
        ends = tuple((a, b, c) for a in (-1, 0, 1) for b in (-1, 1) for c in (-1, 0, 1))
    nbs = side + ends if (caps or kind in ("sphere", "dome", "pyramid")) else side
    shell = set()
    for (x, y, z) in solid:
        if any((x + a, y + b, z + c) not in solid for a, b, c in nbs):
            shell.add((x, y, z))
    return shell


def apply_cells(design, cells, replace=True, slot=None):
    """Put `cells` into the design and stand the turtle on the first one (so the shape is reachable)."""
    if replace:
        design.sel = set()
        design.place = {}
    if not cells:
        return 0
    start = min(cells, key=lambda c: (c[2], c[1], abs(c[0] - (design.w + 1) / 2.0), c[0]))
    design.tx, design.ty, design.tz = start
    for c in cells:
        design.set_cell(c[0], c[1], c[2], True, slot=slot)
    design.sel.discard(design.turtle)
    design.place.pop(design.turtle, None)
    return len(cells)


def _mineshaft(d):
    cells = set()
    for z in range(1, d.d + 1):
        for y in range(1, 4):
            for x in range(3, 6):
                cells.add((x, y, z))
    for x in range(1, d.w + 1):                       # a cross tunnel half way
        for y in range(1, 4):
            for z in range(d.d // 2, d.d // 2 + 3):
                cells.add((x, y, z))
    return cells


TEMPLATES = [
    ("storage", "Storage room", "A roomy 11 x 9 x 4 hall for chests.", (11, 9, 4),
     lambda d: shape_cells("box", d.w, d.d, d.h)),
    ("mineshaft", "Mineshaft with a cross tunnel", "3 wide, 3 tall tunnel with a side tunnel.", (9, 24, 3),
     _mineshaft),
    ("tower", "Round tower shaft", "A 9 wide round shaft, 24 high.", (9, 9, 24),
     lambda d: shape_cells("cylinder", d.w, d.d, d.h)),
    ("stairs", "Staircase up", "A 3 wide staircase climbing 12 blocks.", (5, 13, 13),
     lambda d: shape_cells("stairs", d.w, d.d, d.h)),
    ("cave", "Round cave", "A 13 wide sphere to dig out.", (13, 13, 13),
     lambda d: shape_cells("sphere", d.w, d.d, d.h)),
    ("pyramid", "Pyramid chamber", "A 15 wide solid pyramid, 8 high.", (15, 15, 8),
     lambda d: shape_cells("pyramid", d.w, d.d, d.h)),
]


def template_design(key):
    for k, title, _blurb, (w, dd, h), fn in TEMPLATES:
        if k == key:
            design = Design(w, dd, h)
            design.name = title
            apply_cells(design, fn(design))
            return design
    raise KeyError(key)
# Reads Minecraft schematics (.nbt / .schem) so a build can be imported as a design. Blocks that cannot be dug or placed are skipped (NBT_SKIP).
# ---------------------------------------------------------------------------- schematic import
NBT_SKIP = {"air", "cave_air", "void_air", "water", "lava", "bubble_column", "fire", "soul_fire", "light",
            "barrier", "structure_void", "structure_block", "jigsaw", "moving_piston", "piston_head"}
NBT_REMAP = {"wall_torch": "torch", "redstone_wall_torch": "redstone_torch", "soul_wall_torch": "soul_torch",
             "redstone_wire": "redstone", "tripwire": "string", "wheat": "wheat_seeds", "carrots": "carrot",
             "potatoes": "potato", "beetroots": "beetroot_seeds", "melon_stem": "melon_seeds",
             "pumpkin_stem": "pumpkin_seeds", "sweet_berry_bush": "sweet_berries", "cocoa": "cocoa_beans",
             "kelp_plant": "kelp", "tall_seagrass": "seagrass", "frosted_ice": "ice", "bamboo_sapling": "bamboo",
             "cave_vines": "glow_berries", "cave_vines_plant": "glow_berries", "tall_grass": "short_grass",
             "grass": "short_grass", "lava_cauldron": "cauldron", "water_cauldron": "cauldron"}


class SchematicError(Exception):
    pass


def read_nbt(raw):
    """Parse (optionally gzipped) NBT bytes into plain Python values: the root compound as a dict."""
    if raw[:2] == b"\x1f\x8b":
        raw = gzip.decompress(raw)
    pos = [0]

    def take(n):
        if pos[0] + n > len(raw):
            raise SchematicError("The file ends too early - is it damaged?")
        b = raw[pos[0]:pos[0] + n]
        pos[0] += n
        return b

    def string():
        return take(struct.unpack(">H", take(2))[0]).decode("utf-8", "replace")

    def payload(t):
        if t == 1:
            return struct.unpack(">b", take(1))[0]
        if t == 2:
            return struct.unpack(">h", take(2))[0]
        if t == 3:
            return struct.unpack(">i", take(4))[0]
        if t == 4:
            return struct.unpack(">q", take(8))[0]
        if t == 5:
            return struct.unpack(">f", take(4))[0]
        if t == 6:
            return struct.unpack(">d", take(8))[0]
        if t == 7:
            n = struct.unpack(">i", take(4))[0]
            return take(n)
        if t == 8:
            return string()
        if t == 9:
            et = take(1)[0]
            n = struct.unpack(">i", take(4))[0]
            if n > 20_000_000:
                raise SchematicError("That file is too big.")
            return [payload(et) for _ in range(n)]
        if t == 10:
            out = {}
            while True:
                tt = take(1)[0]
                if tt == 0:
                    return out
                key = string()
                out[key] = payload(tt)
        if t == 11:
            n = struct.unpack(">i", take(4))[0]
            return list(struct.unpack(">%di" % n, take(4 * n)))
        if t == 12:
            n = struct.unpack(">i", take(4))[0]
            return list(struct.unpack(">%dq" % n, take(8 * n)))
        raise SchematicError("Unknown data in the file (type %d)." % t)

    if take(1)[0] != 10:
        raise SchematicError("That is not a Minecraft structure file.")
    string()
    return payload(10)


def _clean_name(n):
    n = str(n).split("[", 1)[0]
    return n if ":" in n else "minecraft:" + n


def _litematic_blocks(root):
    regions = root.get("Regions")
    if not isinstance(regions, dict) or not regions:
        raise SchematicError("No regions found in that Litematica file.")
    out = {}
    for reg in regions.values():
        size = reg["Size"]
        pos = reg.get("Position", {"x": 0, "y": 0, "z": 0})
        sx, sy, sz = abs(size["x"]), abs(size["y"]), abs(size["z"])
        ox = pos["x"] + (size["x"] + 1 if size["x"] < 0 else 0)
        oy = pos["y"] + (size["y"] + 1 if size["y"] < 0 else 0)
        oz = pos["z"] + (size["z"] + 1 if size["z"] < 0 else 0)
        palette = [_clean_name(p.get("Name", "minecraft:air")) for p in reg["BlockStatePalette"]]
        bits = max(2, (len(palette) - 1).bit_length())
        longs = [v & 0xFFFFFFFFFFFFFFFF for v in reg["BlockStates"]]
        mask = (1 << bits) - 1
        i = 0
        for y in range(sy):
            for z in range(sz):
                for x in range(sx):
                    bp = i * bits
                    i += 1
                    li, off = bp >> 6, bp & 63
                    if li >= len(longs):
                        continue
                    v = longs[li] >> off
                    if off + bits > 64 and li + 1 < len(longs):
                        v |= longs[li + 1] << (64 - off)
                    idx = v & mask
                    if idx < len(palette):
                        out[(ox + x, oy + y, oz + z)] = palette[idx]
    return out


def _sponge_blocks(root):
    if "Schematic" in root and isinstance(root["Schematic"], dict):
        root = root["Schematic"]
    w, h, l = root["Width"] & 0xFFFF, root["Height"] & 0xFFFF, root["Length"] & 0xFFFF
    if "Blocks" in root:                                  # version 3
        pal, data = root["Blocks"]["Palette"], root["Blocks"]["Data"]
    else:
        pal, data = root["Palette"], root["BlockData"]
    names = {int(i): _clean_name(n) for n, i in pal.items()}
    vals, cur, shift = [], 0, 0
    for b in data:
        cur |= (b & 0x7F) << shift
        if b & 0x80:
            shift += 7
        else:
            vals.append(cur)
            cur, shift = 0, 0
    out = {}
    i = 0
    for y in range(h):
        for z in range(l):
            for x in range(w):
                if i < len(vals):
                    out[(x, y, z)] = names.get(vals[i], "minecraft:air")
                i += 1
    return out


def _structure_blocks(root):
    pal = [_clean_name(p.get("Name", "minecraft:air")) for p in root["palette"]]
    out = {}
    for b in root["blocks"]:
        x, y, z = b["pos"]
        out[(x, y, z)] = pal[b["state"]]
    return out


def load_schematic(path):
    """Read a .litematic / .schem / .nbt file: returns {(x, y, z): 'minecraft:name'} (0-based, air kept)."""
    try:
        with open(path, "rb") as fh:
            root = read_nbt(fh.read(60_000_000))
    except OSError as ex:
        raise SchematicError("Could not read that file: %s" % ex)
    try:
        if "Regions" in root:
            return _litematic_blocks(root)
        if "Palette" in root or "Schematic" in root or "Blocks" in root:
            return _sponge_blocks(root)
        if "palette" in root and "blocks" in root:
            return _structure_blocks(root)
    except (KeyError, TypeError, IndexError) as ex:
        raise SchematicError("That file is laid out in a way I don't understand (%s)." % ex)
    raise SchematicError("I can open .litematic, .schem and structure .nbt files - this isn't one of them.")


def _rgb(item):
    c = item_color(item)
    return int(c[1:3], 16), int(c[3:5], 16), int(c[5:7], 16)


def schematic_design(blocks, name="Imported build", margin=True):
    """Turn the blocks of a build into a design: every block gets dug and replaced by the same block, so
    it works in solid ground or open air. Only 8 kinds fit in the turtle: the rarer ones become
    the most similar colour of the 8 most common. Returns (design, report)."""
    counts = {}
    cells = {}
    for (x, y, z), n in blocks.items():
        short = n.split(":", 1)[-1]
        if short in NBT_SKIP:
            continue
        short = NBT_REMAP.get(short, short)
        item = "minecraft:" + short if n.startswith("minecraft:") else n
        if n.startswith("minecraft:"):
            item = "minecraft:" + short
        cells[(x, y, z)] = item
        counts[item] = counts.get(item, 0) + 1
    if not cells:
        raise SchematicError("That build has no blocks in it.")
    xs, ys, zs = [c[0] for c in cells], [c[1] for c in cells], [c[2] for c in cells]
    sx, sy, sz = max(xs) - min(xs) + 1, max(ys) - min(ys) + 1, max(zs) - min(zs) + 1
    pad = 1 if (margin and sz < MAXDIM) else 0
    if max(sx, sy, sz + pad) > MAXDIM:
        raise SchematicError("That build is %d x %d x %d. The biggest I can dig is %d in each direction - "
                             "trim it in Litematica/WorldEdit first." % (sx, sy, sz, MAXDIM))
    ranked = sorted(counts, key=lambda k: (-counts[k], k))
    chosen = ranked[:MAX_SUPPLY_SLOTS]
    mapping = {}
    for item in ranked:
        if item in chosen:
            mapping[item] = item
        else:
            r, g, b = _rgb(item)
            mapping[item] = min(chosen, key=lambda c: sum((u - v) ** 2 for u, v in zip(_rgb(c), (r, g, b))))
    des = Design(sx, sz + pad, sy)
    des.name = name
    for i, item in enumerate(chosen):
        des.inv[i + 1] = item
    slot_of = {item: i + 1 for i, item in enumerate(chosen)}
    placed = {}
    for (x, y, z), item in cells.items():
        placed[(x - min(xs) + 1, y - min(ys) + 1, z - min(zs) + 1 + pad)] = slot_of[mapping[item]]
    # where the turtle stands: in the spare row in front of the build, at a column that has a block next to it
    start = None
    if pad:
        for (x, y, z) in sorted(placed, key=lambda c: (c[1], abs(c[0] - (sx + 1) / 2.0), c[0])):
            if z == 2:
                start = (x, y, 1)
                break
    if start is not None:
        des.tx, des.ty, des.tz = start
    else:
        first = min(placed, key=lambda c: (c[2], c[1], abs(c[0] - (sx + 1) / 2.0), c[0]))
        des.tx, des.ty, des.tz = first
    for c, slot in placed.items():
        des.set_cell(c[0], c[1], c[2], True, slot=slot)
    skipped = sum(1 for c in placed if c == des.turtle)
    report = {"blocks": len(placed) - skipped, "kinds": len(counts), "mapped": len(counts) - len(chosen) if len(counts) > len(chosen) else 0,
              "size": (sx, sz, sy), "unreachable": build_run(des)[2], "items": [(i, counts[i]) for i in chosen]}
    return des, report
# Automation jobs: settings, validation and defaults for the ready-made turtle programs (tree farm, smelter, crafter, miner, scout,
# hauler, storage keeper, foreman), plus the colony helpers (shopping list, layout).
# Versions: the shopping list (colony_materials) follows the Foreman's recipes - 7.4 added the hopper (5 iron + a chest), 7.5 added spare redstone;
# colony_layout leaves 10 blocks between jobs since 7.8.
# ---------------------------------------------------------------------------- automation jobs
# Tree farm, auto smelter and auto crafter are ready-made turtle programs with a few settings.
SAPLINGS = [("minecraft:oak_sapling", "Oak"), ("minecraft:spruce_sapling", "Spruce"), ("minecraft:birch_sapling", "Birch"),
            ("minecraft:acacia_sapling", "Acacia"), ("minecraft:cherry_sapling", "Cherry"),
            ("minecraft:mangrove_propagule", "Mangrove"), ("any", "Any sapling it finds")]
AUTO_KINDS = [("treefarm", "Tree farm"), ("smelter", "Auto smelter"), ("crafter", "Auto crafter"),
              ("hauler", "Hauler (carries items between jobs)"), ("keeper", "Storage keeper (chest warehouse)"), ("miner", "Miner (finds resources)"), ("scout", "Scout (maps the world)"),
              ("agent", "Agent (starts jobs on demand)"), ("foreman", "Foreman (sets up the other turtles)")]
MINER_RESOURCES = [("coal", "Coal"), ("iron", "Iron"), ("copper", "Copper"), ("gold", "Gold"), ("redstone", "Redstone"),
                   ("lapis", "Lapis"), ("diamond", "Diamond"), ("emerald", "Emerald")]

TREE_DEFAULT = {"kind": "treefarm", "name": "Tree farm", "cols": 3, "rows": 3, "spacing": 4,
                "sapling": "minecraft:oak_sapling", "bonemeal": False, "wait": 600, "cycles": 0, "chest": True}
SMELTER_DEFAULT = {"kind": "smelter", "name": "Auto smelter", "furnaces": 4, "fuel": "minecraft:coal", "once": False}
HAULER_DEFAULT = {"kind": "hauler", "name": "Hauler", "legs": [{"from": "", "to": "", "item": ""}], "wait": 20, "cycles": 0}
KEEPER_DEFAULT = {"kind": "keeper", "name": "Storage keeper", "length": 8, "wait": 10, "rescan": 1800}
FOREMAN_DEFAULT = {"kind": "foreman", "name": "Foreman", "jobs": [], "dispatch": True, "build": True, "agent_url": "", "launcher_url": ""}
KIT_TAGS = ("chest", "furnace", "sapling", "coal", "bonemeal")
MINER_DEFAULT = {"kind": "miner", "name": "Miner", "depth": 20, "reach": 30, "rib": 12,
                "want": [k for k, _l in MINER_RESOURCES]}
SCOUT_DEFAULT = {"kind": "scout", "name": "Scout", "radius": 24, "up": 8, "down": 4}
AGENT_DEFAULT = {"kind": "agent", "name": "Agent"}
CRAFTER_DEFAULT = {"kind": "crafter", "name": "Auto crafter", "grid": [None] * 9, "out": "", "total": 0, "once": False}


def auto_default(kind):
    base = {"treefarm": TREE_DEFAULT, "smelter": SMELTER_DEFAULT, "crafter": CRAFTER_DEFAULT,
            "scout": SCOUT_DEFAULT, "agent": AGENT_DEFAULT, "miner": MINER_DEFAULT, "hauler": HAULER_DEFAULT, "keeper": KEEPER_DEFAULT, "foreman": FOREMAN_DEFAULT}[kind]
    out = dict(base)
    if kind == "crafter":
        out["grid"] = [None] * 9
    if kind == "hauler":
        out["legs"] = [dict(l) for l in base["legs"]]
    if kind == "foreman":
        out["jobs"] = []
    return out


def _int(v, lo, hi, what):
    try:
        n = int(v)
    except (TypeError, ValueError):
        raise ValueError("%s must be a whole number." % what)
    if not lo <= n <= hi:
        raise ValueError("%s must be between %d and %d." % (what, lo, hi))
    return n


def clean_auto(p):
    """Validate / normalise one automation job (a dict). Raises ValueError with a friendly message."""
    kind = p.get("kind")
    if kind not in dict(AUTO_KINDS):
        raise ValueError("Unknown job type.")
    out = {"kind": kind, "name": clean_name(p.get("name") or dict(AUTO_KINDS)[kind])}
    label = str(p.get("label") or "").strip()
    if label:                                    # the computer label the turtle gives itself on its first start (if it has none)
        if not re.fullmatch(r"[A-Za-z0-9 _.\-]{1,30}", label):
            raise ValueError("The turtle's name may use letters, numbers, spaces and _ . - (up to 30).")
        out["label"] = label
    if kind == "treefarm":
        out["cols"] = _int(p.get("cols", 3), 1, 12, "Trees per row")
        out["rows"] = _int(p.get("rows", 3), 1, 12, "Rows")
        out["spacing"] = _int(p.get("spacing", 4), 3, 8, "Spacing")
        sap = p.get("sapling", "minecraft:oak_sapling")
        if sap not in dict(SAPLINGS) and not clean_item(sap):
            raise ValueError("Pick a sapling.")
        out["sapling"] = sap
        out["bonemeal"] = bool(p.get("bonemeal"))
        out["wait"] = _int(p.get("wait", 600), 30, 7200, "Wait between checks (seconds)")
        out["cycles"] = _int(p.get("cycles", 0), 0, 999, "Cycles")
        out["chest"] = bool(p.get("chest", True))
    elif kind == "smelter":
        out["furnaces"] = _int(p.get("furnaces", 4), 1, 16, "Furnaces")
        fuel = clean_item(p.get("fuel") or "minecraft:coal")
        if not fuel:
            raise ValueError("Pick the fuel item.")
        out["fuel"] = fuel
        out["once"] = bool(p.get("once"))
    elif kind == "hauler":
        legs = []
        for l in (p.get("legs") or []):
            if not isinstance(l, dict):
                raise ValueError("Bad leg.")
            a, b, it = (str(l.get(k) or "").strip() for k in ("from", "to", "item"))
            if not (a or b or it):
                continue                                        # an empty row
            for what, v in (("From", a), ("To", b)):
                if not v or not re.fullmatch(r"[A-Za-z0-9 _.:\-]{1,40}", v):
                    raise ValueError("%s needs the name of one of your jobs (letters, numbers, spaces)." % what)
            if it and not re.fullmatch(r"[a-z0-9_:.\-]{1,40}", it):
                raise ValueError("The item filter is part of an item name, like  log  or  charcoal.")
            legs.append({"from": a, "to": b, "item": it})
        if not legs:
            raise ValueError("Add at least one leg: where to take items from and where to put them.")
        if len(legs) > 6:
            raise ValueError("A hauler can have up to 6 legs.")
        out["legs"] = legs
        out["wait"] = _int(p.get("wait", 20), 5, 600, "Wait when idle (seconds)")
        out["cycles"] = _int(p.get("cycles", 0), 0, 9999, "Rounds")
    elif kind == "keeper":
        out["length"] = _int(p.get("length", 8), 1, 30, "Corridor length")
        out["wait"] = _int(p.get("wait", 10), 3, 300, "Wait between checks (seconds)")
        out["rescan"] = _int(p.get("rescan", 1800), 0, 86400, "Re-count every chest (seconds, 0 = never)")
    elif kind == "miner":
        out["depth"] = _int(p.get("depth", 20), 4, 120, "Depth")
        out["reach"] = _int(p.get("reach", 30), 3, 96, "Main tunnel length")
        out["rib"] = _int(p.get("rib", 12), 0, 32, "Side tunnel length")
        want = p.get("want", [k for k, _l in MINER_RESOURCES])
        if not isinstance(want, (list, tuple)) or not want or any(w not in dict(MINER_RESOURCES) for w in want):
            raise ValueError("Pick at least one resource to look for.")
        out["want"] = [k for k, _l in MINER_RESOURCES if k in want]
    elif kind == "scout":
        out["radius"] = _int(p.get("radius", 24), 4, 64, "Radius")
        out["up"] = _int(p.get("up", 8), 0, 40, "Height above the start")
        out["down"] = _int(p.get("down", 4), 0, 40, "Depth below the start")
    elif kind == "agent":
        pass
    elif kind == "foreman":
        jobs = []
        for j in (p.get("jobs") or [])[:16]:
            if not isinstance(j, dict) or j.get("kind") not in dict(AUTO_KINDS) or j.get("kind") == "foreman":
                raise ValueError("Bad job in the foreman's list.")
            slug = str(j.get("slug") or "")
            if not re.fullmatch(r"[a-z0-9_\-]{1,40}", slug):
                raise ValueError("Bad program name in the foreman's list.")
            foot = j.get("foot")
            if foot is not None:
                if not (isinstance(foot, (list, tuple)) and len(foot) == 6):
                    raise ValueError("Bad footprint in the foreman's list.")
                foot = [_int(v, -999, 999, "Footprint") for v in foot]
            kit = []
            for k in (j.get("kit") or [])[:8]:
                if not (isinstance(k, (list, tuple)) and len(k) == 2 and k[0] in KIT_TAGS):
                    raise ValueError("Bad kit in the foreman's list.")
                kit.append([k[0], _int(k[1], 0, 256, "Kit amount")])
            jobs.append({"name": clean_name(j.get("name") or slug), "slug": slug, "kind": j["kind"],
                         "furnaces": _int(j.get("furnaces", 0), 0, 16, "Furnaces"), "foot": foot,
                         "kit": kit, "crafty": bool(j.get("crafty"))})
        out["jobs"] = jobs
        out["dispatch"] = bool(p.get("dispatch", True))
        out["build"] = bool(p.get("build", True))
        for k in ("agent_url", "launcher_url"):
            v = str(p.get(k) or "")
            if v and not re.fullmatch(r"https?://[A-Za-z0-9._~:/?#@!$&'()*+,;=%\-]{1,300}", v):
                raise ValueError("Bad address for the first-start programs.")
            out[k] = v
    else:
        grid = p.get("grid") or [None] * 9
        if not isinstance(grid, list) or len(grid) != 9:
            raise ValueError("The recipe needs 9 cells.")
        cells = []
        for g in grid:
            if g in (None, "", False):
                cells.append(None)
            else:
                n = clean_item(g)
                if not n:
                    raise ValueError("Bad item in the recipe grid.")
                cells.append(n)
        if not any(cells):
            raise ValueError("Put at least one ingredient in the recipe grid.")
        out["grid"] = cells
        out["out"] = clean_item(p.get("out")) if p.get("out") else ""
        out["total"] = _int(p.get("total", 0), 0, 99999, "Crafts")
        out["once"] = bool(p.get("once"))
    return out


def _lua_value(v):
    if v is None or v is False:
        return "false"
    if v is True:
        return "true"
    if isinstance(v, (int, float)):
        return str(v)
    if isinstance(v, str):
        return json.dumps(v)
    if isinstance(v, (list, tuple)):
        return "{" + ", ".join(_lua_value(x) for x in v) + "}"
    if isinstance(v, dict):
        return "{" + ", ".join("%s = %s" % (k, _lua_value(x)) for k, x in sorted(v.items())) + "}"
    raise TypeError(v)


def auto_slug(p):
    return slugify(p["name"])


def generate_auto_lua(p, live_url=""):
    """The turtle program for one automation job."""
    p = clean_auto(p)
    tmpl = {"treefarm": AUTO_TREEFARM_TEMPLATE, "smelter": AUTO_SMELTER_TEMPLATE, "crafter": AUTO_CRAFTER_TEMPLATE,
            "scout": AUTO_SCOUT_TEMPLATE, "agent": AUTO_AGENT_TEMPLATE, "miner": AUTO_MINER_TEMPLATE, "hauler": AUTO_HAULER_TEMPLATE, "keeper": AUTO_KEEPER_TEMPLATE,
            "foreman": AUTO_FOREMAN_TEMPLATE}[p["kind"]]
    plan = {k: v for k, v in p.items() if k != "kind"}
    if p["kind"] == "crafter":
        plan.pop("out", None)
    plan["kind"] = p["kind"]
    plan["live"] = normalize_live_url(live_url)
    text = "local PLAN = " + _lua_value(plan)
    return ("-- built by Carve Designer v%s\n" % VERSION) + tmpl.replace("--@@PLAN@@", text, 1).replace("--@@COMMON@@", AUTO_COMMON_LUA, 1)


def auto_summary(p):
    """Plain words (and rough numbers) about what a job needs, shown before uploading."""
    p = clean_auto(p)
    lines, warns = [], []
    if p["kind"] == "treefarm":
        n = p["cols"] * p["rows"]
        sx = p["spacing"] * (p["cols"] + 1)
        sz = p["spacing"] * p["rows"] + 1
        lines.append("%d trees in a grid of %d x %d, about %d x %d blocks of flat ground (dirt or grass)." % (n, p["cols"], p["rows"], sx, sz))
        lines.append("Slot 1: at least %d %s. %s" % (n, dict(SAPLINGS).get(p["sapling"], p["sapling"]).lower() + " saplings"
                     if p["sapling"] in dict(SAPLINGS) else p["sapling"],
                     "Slot 2: bone meal (trees grow at once)." if p["bonemeal"] else "No bone meal: it waits %d s between rounds." % p["wait"]))
        lines.append("A chest right behind the start collects the logs." if p["chest"] else "No chest: you have to empty it.")
        lines.append("A free walkway: the column at the start and the lane in front of each row.")
        if p["spacing"] < 4:
            warns.append("Trees closer than 4 apart grow into each other.")
    elif p["kind"] == "smelter":
        lines.append("%d furnaces in a row, 2 blocks in front of the start. Run it once with  setup  and %d furnaces in its inventory to place them." % (p["furnaces"], p["furnaces"]))
        lines.append("Chest BEHIND the start: raw items + %s. Chest on the LEFT: results." % item_label(p["fuel"]))
        lines.append("One stack per furnace per round; about %d s per round for full stacks." % (64 * 10 + 6))
        lines.append("One %s smelts 8 items." % item_label(p["fuel"]).lower())
        lines.append("No coal? Give it logs: it burns about 40%% of them to make the first charcoal, and once it holds 32 charcoal it burns that instead. It keeps up to a stack of charcoal for fuel and sends the rest to the output chest.")
        lines.append("It places its own chests (digging out earth where they go) from chests in its inventory.")
    elif p["kind"] == "hauler":
        for l in p["legs"]:
            lines.append("Takes %s from the output chest of '%s' and puts it in the input chest of '%s'." % (
                ("items with '%s' in the name" % l["item"]) if l["item"] else "everything", l["from"], l["to"]))
        lines.append("It asks the app where those chests are, so it needs live reporting, its own start position, and the start positions of those jobs (Fleet tab or GPS).")
        lines.append("It stands on top of each chest, so keep the block above every chest free. It never digs.")
        lines.append("Fuel: give it some coal or charcoal; it also burns charcoal it is carrying when it runs low.")
        lines.append("Stacks that don't match the filter go straight back; if a chest has 14 or more stacks of other items in front, it may not reach the matching ones.")
        warns.append("Without live reporting nobody can tell it where the chests are.")
    elif p["kind"] == "keeper":
        lines.append("A warehouse that builds itself: a corridor of up to %d steps with 4 storage chests per step (right, left, above, below) = up to %d chests, %d stacks." % (
            p["length"], p["length"] * 4, p["length"] * 4 * 27))
        lines.append("Start it with a chest in the first slot and fuel in another. It places the DROP chest behind the start and the PICKUP chest on the left, then one storage chest at a time as it needs room.")
        lines.append("Put items in the drop chest (or let a hauler do it): they are sorted into the chests, one kind of item per chest where it can. Chests you put in there are kept and used to grow the warehouse.")
        lines.append("It remembers what is in every chest and reports it to the Storage tab of the Fleet page. Ask for an item there and it appears in the pickup chest.")
        lines.append("Needs live reporting for the web page. It digs its corridor, so pick a spot with room (about 3 wide, 3 high and %d long)." % (p["length"] + 2))
        warns.append("Without live reporting it still stores things, but you can't see or order items from the website.")
    elif p["kind"] == "miner":
        ribs = (p["reach"] // 3) * 2 if p["rib"] else 0
        fuel = 2 * p["depth"] + 2 * p["reach"] + 2 * p["rib"] * ribs
        lines.append("Digs a shaft %d blocks straight down from the start, a main tunnel %d blocks long, and %d side tunnels of %d blocks (every 3 blocks)." % (
            p["depth"], p["reach"], ribs, p["rib"]))
        lines.append("Looks for: %s. It checks every wall it passes and mines the whole vein." % ", ".join(
            dict(MINER_RESOURCES)[w].lower() for w in p["want"]))
        lines.append("Chest right BEHIND the start: it empties itself there when full and takes finds back up. Stone and dirt are thrown away.")
        lines.append("Fuel for the whole run: about %d. Give it that much coal to start; coal ore it finds refuels it." % fuel)
        lines.append("Diamonds are most common about 55-60 blocks below sea level (y = -58); coal and iron are everywhere above.")
        if fuel > 2500:
            warns.append("That is a lot of fuel (one coal gives 80). Start it with a stack of coal.")
        warns.append("Never mines next to lava on purpose, but unlit caves have mobs: place it somewhere you can defend.")
    elif p["kind"] == "scout":
        lines.append("Explores up to %d blocks around the start, %d up and %d down, and reports every block it sees to the Fleet map." % (
            p["radius"], p["up"], p["down"]))
        lines.append("It never digs, places or enters water and lava. It flies through open air and over ledges the way a turtle can.")
        lines.append("Needs fuel: coal (or logs) in its inventory. Stand it on the START cell facing forward; it returns there when done.")
        lines.append("The map needs live reporting ticked at upload, and the turtle's start position (GPS, or typed in the Fleet tab).")
        if p["radius"] > 40:
            warns.append("A big radius takes a long time and a lot of fuel.")
    elif p["kind"] == "foreman":
        lines.append("Builds the other turtles of the colony so you only start this one by hand. It crafts each turtle (computer, turtle, diamond pickaxe; crafty for the crafter) from the chest of materials behind it, places it in front, boots it with a disk drive and floppy that install the first-start programs, hands it its chests, furnaces, saplings and coal, and sends it to its job's start position.")
        lines.append("It needs a pickaxe and a crafting table: a crafty turtle, or a plain turtle with a crafting table in its inventory (it equips it itself). Put the materials listed in the Colony tab in the chest behind it, an empty chest on its left (sorting), and a few coal in its own inventory.")
        lines.append("Needs live reporting, its own start position, and the jobs' positions (stations marked in the pixel designer, or typed). Jobs without a position are laid out in a row to its right.")
        lines.append("Set 'build' off in the program (old mode) to only place chests and furnaces and use agents that are already waiting.")
        warns.append("Without live reporting it can't know where anything goes.")
    elif p["kind"] == "agent":
        lines.append("Sits idle and reports to the Fleet tab until it is told to start a program there, or by another turtle with  carve start <its id> <program>.")
        lines.append("Needs the  carve  menu installed on this turtle, and live reporting ticked at upload.")
        warns.append("Without live reporting nobody can reach it.")
    else:
        used = [g for g in p["grid"] if g]
        kinds = sorted(set(used))
        lines.append("Crafts the recipe over and over: %s." % ", ".join("%d x %s" % (used.count(k), item_label(k)) for k in kinds))
        lines.append("Needs a crafty turtle (turtle + crafting table). Ingredients in the chest BEHIND, results go to the chest on the LEFT.")
        if p["total"]:
            lines.append("Stops after %d crafts." % p["total"])
    return {"lines": lines, "warnings": warns}


# ---------------------------------------------------------------- the colony starter set
def colony_starter():
    """The four turtles that start a colony (storage keeper, tree farm, smelter, crafter) and the hauler that links them."""
    comp = dict(CRAFTER_DEFAULT, name="Compressor", grid=["minecraft:charcoal"] * 9)
    haul = dict(HAULER_DEFAULT, name="Hauler", legs=[
        {"from": "Tree farm", "to": "Smelter", "item": "log"},
        {"from": "Smelter", "to": "Compressor", "item": "charcoal"},
        {"from": "Compressor", "to": "Storage keeper", "item": "charcoal"}])
    jobs = [dict(FOREMAN_DEFAULT), dict(KEEPER_DEFAULT, name="Storage keeper"), dict(TREE_DEFAULT, name="Tree farm"),
            dict(SMELTER_DEFAULT, name="Smelter"), comp, haul]
    return colony_label([clean_auto(j) for j in jobs])


def colony_kit(job):
    """What a new turtle for this job is handed (besides coal): [[item tag, amount]]."""
    k = job["kind"]
    if k == "keeper":
        return [["chest", 8]]
    if k == "treefarm":
        return [["sapling", job["cols"] * job["rows"]]] + ([["chest", 1]] if job.get("chest") else []) + ([["bonemeal", 16]] if job.get("bonemeal") else [])
    if k == "smelter":
        return [["furnace", job["furnaces"]], ["chest", 2]]
    if k == "crafter":
        return [["chest", 2]]
    if k == "miner":
        return [["chest", 1]]
    return []


def colony_foreman(jobs):
    """The foreman job of a colony: its list of the other jobs (name, program, kind, furnaces, footprint) is rebuilt from the
    current jobs, so it always matches what is uploaded. Returns the jobs with the foreman first (added when missing)."""
    foreman = next((j for j in jobs if j["kind"] == "foreman"), None) or clean_auto(FOREMAN_DEFAULT)
    others = [j for j in jobs if j["kind"] != "foreman"]
    foreman = dict(foreman, jobs=[{"name": j["name"], "slug": auto_slug(j), "kind": j["kind"],
                                   "furnaces": j.get("furnaces", 0) if j["kind"] == "smelter" else 0,
                                   "foot": auto_footprint(j), "kit": colony_kit(j), "crafty": j["kind"] == "crafter"}
                                  for j in others if j["kind"] != "agent"])
    foreman = clean_auto(foreman)
    return colony_label([foreman] + others)


def colony_materials(jobs):
    """What the Foreman needs in its supply chest to build and equip every other turtle:
    {"items": {item: count}, "turtles": n, "crafty": n, "lines": [plain words]}. Ready-made chests, furnaces and planks are accepted too."""
    mine = [j for j in jobs if j["kind"] not in ("foreman", "agent")]
    n = len(mine)
    crafty = sum(1 for j in mine if j["kind"] == "crafter")
    kit = [colony_kit(j) for j in mine]
    chests = sum(a for ks in kit for t, a in ks if t == "chest")
    furn = sum(a for ks in kit for t, a in ks if t == "furnace")
    saplings = sum(a for ks in kit for t, a in ks if t == "sapling")
    bone = sum(a for ks in kit for t, a in ks if t == "bonemeal")
    # v7.4/v7.5: the Foreman makes one extra chest per kit carrier and one for the hopper (+2 chests); iron has +5 for the hopper, redstone has spares.
    planks = n * 8 + 2 * (-(-n // 2)) + crafty * 4 + (chests + (2 if n else 0)) * 8          # +1 chest carries each kit to its new turtle (and is taken back), +1 goes into the hopper that loads the floppy
    items = {"iron ingots": 7 * n + 5, "stone": 7 * n + 7, "redstone": n + 5, "diamonds": 3 * n,
             "glass": 6 * (-(-n // 16)) if n else 0, "logs": -(-planks // 4), "sugar cane": 3,
             "cobblestone": furn * 8, "coal": 16 * n + 16, "saplings": saplings, "bone meal": bone}
    items = {k: v for k, v in items.items() if v}
    lines = ["%d %s" % (v, k) for k, v in items.items()]
    return {"items": items, "turtles": n, "crafty": crafty, "lines": lines, "chests": chests, "furnaces": furn}


def colony_materials_text(jobs):
    """The Foreman's shopping list, in plain words."""
    m = colony_materials(jobs)
    out = ["The Foreman builds %d turtles (%d of them crafty) from what you put in its CHEST:" % (m["turtles"], m["crafty"])]
    out += ["  " + l for l in m["lines"]]
    out += ["", "  (planks, chests, furnaces, glass panes and paper are fine instead of logs, cobblestone,",
            "   glass and sugar cane; stone means smelted cobblestone.)",
            "", "Set up the Foreman like this:",
            "  - a chest with those materials BEHIND it, an empty chest on its LEFT",
            "  - a few coal in its own inventory for fuel",
            "  - free space in FRONT of it (new turtles appear there) and one block above that",
            "", "Also needed:",
            "  - the Foreman: a turtle with a pickaxe, crafted by hand, plus a crafting table (equipped, or in its inventory)",
            "  - its own start position (and the jobs' positions: marks in the pixel designer, or the Advanced list)",
            "  - 'Upload' first: new turtles download their programs from GitHub",
            "", "Then start the Foreman. Each turtle is built, started, given its items and sent to its position."]
    return "\n".join(out)


def colony_label(jobs):
    """Give every job without a turtle name the next unused Deadlock hero name (in this run's random order), so each turtle names itself on its first start."""
    used = {j.get("label") for j in jobs if j.get("label")}
    out = []
    for j in jobs:
        j = dict(j)
        if not j.get("label"):
            n, name = 1, None
            while name is None:
                for g in NAME_ORDER:
                    cand = g if n == 1 else "%s %d" % (g, n)
                    if cand not in used:
                        name = cand
                        break
                n += 1
            j["label"] = name
            used.add(name)
        out.append(j)
    return out


def colony_extra(jobs, kind):
    """One more job of this kind for a colony, with a name no other job has ("Tree farm 2")."""
    if kind not in dict(AUTO_KINDS):
        raise ValueError("Unknown job type.")
    base = auto_default(kind)
    if kind == "hauler":
        src = next((j for j in jobs if j["kind"] == "hauler"), None)
        if src:
            base["legs"] = [dict(l) for l in src["legs"]]
    if kind == "crafter":
        base["grid"] = ["minecraft:charcoal"] * 9
    taken = {j["name"].lower() for j in jobs}
    name, n = base["name"], 1
    while name.lower() in taken:
        n += 1
        name = "%s %d" % (base["name"], n)
    base["name"] = name
    return colony_label(list(jobs) + [clean_auto(base)])[-1]


def colony_test_variant(job):
    """The same job, shrunk for a quick developer test (small tree farm, short warehouse, few furnaces...)."""
    j = dict(job)
    k = j["kind"]
    if k == "treefarm":
        j.update(cols=2, rows=2, wait=60)
    elif k == "keeper":
        j.update(length=3, wait=5)
    elif k == "smelter":
        j.update(furnaces=2)
    elif k == "miner":
        j.update(depth=6, reach=10, rib=4)
    elif k == "scout":
        j.update(radius=8, up=3, down=2)
    return clean_auto(j)


# v7.8: 10 blocks between the jobs' areas (it was 3) so the sites are clearly separate.
def colony_layout(jobs, origin, gap=10):
    """World start cells for a row of jobs, all facing north, side by side along +x from `origin` (x, y, z) with a gap (10 blocks) between
    their footprints, so a single coordinate is all that has to be typed. Returns {job name: (x, y, z)}."""
    ox, oy, oz = origin
    cursor, out = ox, {}
    for j in jobs:
        f = auto_footprint(j) or [-1, -1, -1, 1, 1, 1]
        x = cursor - f[0]
        out[j["name"]] = (x, oy, oz)
        cursor = x + f[3] + 1 + gap
    return out


def mark_world_face(base_face, mark_face):
    """The compass direction of a station mark (forward / right / back / left of the base design) when the design's
    own forward points base_face."""
    order = ["north", "east", "south", "west"]
    return order[(order.index(base_face) + ("forward", "right", "back", "left").index(mark_face)) % 4]


def base_positions(design, origin, face):
    """World start cells of the jobs marked in the base design. origin = world (x, y, z) of the design's turtle start cell
    (where the Foreman stands) and face = the way it faces. Returns {job name: (x, y, z, facing)}."""
    out = {}
    for name, (x, y, z, f) in design.marks.items():
        w = local_to_world(tuple(origin) + (face,), (x - design.tx, y - design.ty, z - design.tz))
        out[name] = (w[0], w[1], w[2], mark_world_face(face, f))
    return out


COLONY_NEEDS = {
    "foreman": "a turtle with a pickaxe and a crafting table (in its inventory is fine: it equips it), a chest of materials behind it (see the list), an empty chest on its left, some coal.",
    "keeper": "8 or more chests (first slot), some coal. Start this one first.",
    "treefarm": "saplings (about 1 per tree), a chest, optionally bone meal.",
    "smelter": "2 chests, 4 furnaces, some coal.",
    "crafter": "a crafty turtle (turtle + crafting table), 2 chests.",
    "hauler": "some coal. Start it last, once the others are running and have start positions.",
    "miner": "a chest, plenty of coal.",
    "scout": "some coal.",
    "agent": "nothing; it waits for orders.",
}


def colony_guide(jobs):
    """Plain-words start-up list for a colony: what to put in each turtle and in which order to start them."""
    order = ["agent", "keeper", "treefarm", "smelter", "crafter", "miner", "scout", "hauler", "foreman"]
    lines = ["Start the Fleet server (Fleet tab) and make sure 'Include live reporting' is ticked.",
             "For each turtle: stand it on its start cell, set its start position in the Fleet tab (or use GPS), put in:", ""]
    for j in sorted(jobs, key=lambda j: order.index(j["kind"]) if j["kind"] in order else 99):
        lines.append("  %-16s carve %-16s %s" % (j["name"], slugify(j["name"]), COLONY_NEEDS.get(j["kind"], "")))
    lines += ["", "Each turtle gets a Deadlock hero's name when it first reports in.",
              "Watch them in the Fleet tab; the keeper's items are on the Storage page."]
    return "\n".join(lines)


AUTO_COMMON_LUA = r'''-- Shared by every turtle program (it is pasted into each program at its COMMON marker): position tracking, safe movement, fuel,
-- the Fleet reporting (fleetSend) and the screen helper (say).
-- Versions: 7.8 Stop from the Fleet page removes the automatic restart; 8.0 every turtle reports its inventory; 8.2 burn() uses charcoal first.
---------------------------------------------------------------- shared helpers (position, moving, fuel)
-- directions: 1 = +z (forward at start), 2 = +x (right), 3 = -z (back), 4 = -x (left), 5 = up, 6 = down
-- every turtle names itself after a Deadlock hero (by its id) the first time it starts, if it has no label yet
do
  local GODS = { "Abrams", "Bebop", "Dynamo", "Grey Talon", "Haze", "Infernus", "Ivy", "Kelvin", "Lady Geist", "Lash", "McGinnis", "Krill", "Paradox", "Pocket", "Seven", "Shiv", "Vindicta", "Viscous", "Warden", "Wraith", "Yamato", "Calico", "Holliday", "Vyper", "Sinclair", "Mirage", "Drifter", "Victor", "Paige", "Billy", "Rem", "Mo" }
  if os.getComputerLabel and os.setComputerLabel and os.getComputerID and not os.getComputerLabel() then
    pcall(os.setComputerLabel, PLAN.label or GODS[os.getComputerID() % #GODS + 1])   -- the colony's name for it, else by id
  end
end

local DX = { 0, 1, 0, -1, 0, 0 }
local DZ = { 1, 0, -1, 0, 0, 0 }
local DY = { 0, 0, 0, 0, 1, -1 }
local pos = { x = 0, y = 0, z = 0 }
local face = 1
local MARK = "-- carve auto"
local PROGRAM = shell and shell.getRunningProgram and shell.getRunningProgram() or "job"

local function writeFile(name, text)
  local f = fs.open(name, "w")
  if f then f.write(text); f.close() end
end

local function readFile(name)
  if not fs.exists(name) then return nil end
  local f = fs.open(name, "r")
  if not f then return nil end
  local s = f.readAll()
  f.close()
  return s
end

local function savePos()
  writeFile(STATE_FILE, pos.x .. "," .. pos.y .. "," .. pos.z .. "," .. face)
end

local function loadPos()
  local s = readFile(STATE_FILE)
  if not s then return false end
  local x, y, z, f = s:match("^(-?%d+),(-?%d+),(-?%d+),(%d)")
  if not x then return false end
  pos.x, pos.y, pos.z, face = tonumber(x), tonumber(y), tonumber(z), tonumber(f)
  return true
end

local function installStartup()
  local cur = readFile("startup.lua")
  if cur and not cur:find(MARK, 1, true) then return end      -- someone else's startup file: leave it
  writeFile("startup.lua", MARK .. "\nshell.run(\"" .. PROGRAM .. "\", \"resume\")\n")
end

local function removeStartup()
  local cur = readFile("startup.lua")
  if cur and cur:find(MARK, 1, true) then fs.delete("startup.lua") end
end

---------------------------------------------------------------- fleet reporting (optional)
-- Tells the Carve Designer what this turtle is doing (name, place, fuel, message) every few seconds and
-- obeys a "stop" from its Fleet page. If the app isn't there nothing breaks.
local LIVE_URL = PLAN.live or ""
local fleet = { on = LIVE_URL ~= "" and http ~= nil and http.post ~= nil, last = -100, fails = 0, retryAt = 0, status = "",
                done = false, msg = "", act = "", seq = 0, n = 0, total = 0, cmd = nil, arg = "", world = nil, peers = {},
                run = os.epoch and math.floor(os.epoch("utc") / 1000) or 0,
                gpsLast = -100, gpsFails = 0, gpsOk = false, gpsDead = false }
for _, a in ipairs(args) do
  if a == "nolive" then fleet.on = false end
end
if LIVE_URL == "" then
  fleet.status = "live reporting is OFF (uploaded without it)"
elseif not (http and http.post) then
  fleet.status = "the http API is off on this computer"
elseif fleet.on then
  fleet.status = "connecting to " .. LIVE_URL
else
  fleet.status = "live reporting switched off (nolive)"
end

local function jq(s)
  s = tostring(s):gsub('[%c"\\]', function(c)
    if c == '"' then return '\\"' end
    if c == "\\" then return "\\\\" end
    return string.format("\\u%04x", c:byte())
  end)
  return '"' .. s .. '"'
end

-- what I am trying to do this very moment (shown next to the status on the Fleet page)
local function act(text) fleet.act = text end

-- a GPS fix of where the turtle is right now (needs a GPS tower and a wireless modem); nil otherwise
local function gpsFix(now)
  if fleet.gpsDead or not (gps and gps.locate) or now - fleet.gpsLast < 20 then return nil end
  fleet.gpsLast = now
  local ok, x, y, z = pcall(gps.locate, 1)
  if ok and x then fleet.gpsOk, fleet.gpsFails = true, 0; return { x, y, z } end
  fleet.gpsFails = fleet.gpsFails + 1
  if fleet.gpsFails >= 2 and not fleet.gpsOk then fleet.gpsDead = true end
end

-- ---- shared map: every program tells the app what it sees on its way (scouts do it themselves)
local MAP_SHARE = fleet.on and PLAN.kind ~= "scout" and PLAN.map ~= false
local mapSeen, mapCount, mapOut, mapMoves, mapLast = {}, 0, {}, 0, 0
local function mapNote(x, y, z, name)
  local k = ((x + 512) * 1024 + (z + 512)) * 1024 + (y + 512)
  local old = mapSeen[k]
  if old == name then return end
  if old == nil then
    if mapCount >= 8000 then return end
    mapCount = mapCount + 1
  end
  mapSeen[k] = name
  mapOut[#mapOut + 1] = { x, y, z, name }
  if #mapOut > 1500 then table.remove(mapOut, 1) end
end
local function mapInspect(fn)
  local found, data = fn()
  if not found then return "air" end
  return type(data) == "table" and data.name or "unknown"
end
-- called after every move: my own cell is free, and the cell I face (and now and then above and below) is whatever it is
local function mapSee()
  if not MAP_SHARE then return end
  mapNote(pos.x, pos.y, pos.z, "air")
  mapMoves = mapMoves + 1
  local n = mapInspect(turtle.inspect)
  if n then mapNote(pos.x + DX[face], pos.y, pos.z + DZ[face], n) end
  if mapMoves % 4 == 0 then
    n = mapInspect(turtle.inspectUp); if n then mapNote(pos.x, pos.y + 1, pos.z, n) end
    n = mapInspect(turtle.inspectDown); if n then mapNote(pos.x, pos.y - 1, pos.z, n) end
  end
end
local function mapFlush(force)
  if not MAP_SHARE or #mapOut == 0 then return end
  local now = os.clock()
  if not force and #mapOut < 30 and now - mapLast < 10 then return end
  mapLast = now
  while #mapOut > 0 do
    local parts, sent = {}, {}
    for i = 1, math.min(#mapOut, 300) do
      local c = table.remove(mapOut)
      sent[#sent + 1] = c
      parts[#parts + 1] = "[" .. c[1] .. "," .. c[2] .. "," .. c[3] .. "," .. jq(c[4]) .. "]"
    end
    local ok, res = pcall(http.post, { url = LIVE_URL .. "/map", timeout = 5, headers = { ["Content-Type"] = "application/json" },
      body = '{"v":1,"id":' .. os.getComputerID() .. ',"cells":[' .. table.concat(parts, ",") .. "]}" })
    if ok and res then
      pcall(function() res.readAll(); res.close() end)
    else
      for _, c in ipairs(sent) do mapOut[#mapOut + 1] = c end
      break
    end
  end
end

-- what the app answered: "ok [command [argument]]", then "me x y z" (world position) and "peer id name x y z" lines
local function handleReply(reply)
  local cmd, arg = reply:match("^ok (%a+) ?([%w_%-]*)")
  if cmd then fleet.cmd, fleet.arg = cmd, arg or "" end        -- kept until the program has acted on it
  -- v7.8: a Stop from the Fleet page must stay stopped. Before, the turtle's startup file restarted the program the next time the world was opened.
  if cmd == "stop" then fleet.stopAsked = true; os.queueEvent("terminate") end
  fleet.world, fleet.peers = nil, {}
  for line in reply:gmatch("[^\n]+") do
    local gx, gy, gz, gf = line:match("^goto (-?%d+) (-?%d+) (-?%d+) (%d)$")
    if gx then fleet.dest = { tonumber(gx), tonumber(gy), tonumber(gz), tonumber(gf) } end
    local lab = line:match("^label ([%w_]+)$")
    if lab and os.setComputerLabel and not os.getComputerLabel() then pcall(os.setComputerLabel, (lab:gsub("_", " "))) end
    local x, y, z = line:match("^me (-?%d+) (-?%d+) (-?%d+)$")
    if x then fleet.world = { tonumber(x), tonumber(y), tonumber(z) } end
    local id, nm, px, py, pz = line:match("^peer (%d+) (%S+) (-?%d+) (-?%d+) (-?%d+)$")
    if id and #fleet.peers < 6 then
      fleet.peers[#fleet.peers + 1] = { id = tonumber(id), name = nm, x = tonumber(px), y = tonumber(py), z = tonumber(pz) }
    end
  end
end

local function fleetSend(force)
  if not fleet.on then return end
  local now = os.clock()
  if now < fleet.retryAt then return end
  if not force and now - fleet.last < 3 then return end
  fleet.last = now
  fleet.seq = fleet.seq + 1
  local fuel = turtle and turtle.getFuelLevel() or 0
  local label = os.getComputerLabel and os.getComputerLabel() or ""
  local body = table.concat({
    '{"v":1,"seq":' .. fleet.seq, '"id":' .. os.getComputerID(), '"label":' .. jq(label or ""),
    '"name":' .. jq(PLAN.name or ""), '"kind":' .. jq(PLAN.kind or "auto"),
    '"x":' .. pos.x, '"y":' .. pos.y, '"z":' .. pos.z, '"fuel":' .. jq(fuel),
    '"msg":' .. jq(fleet.msg), '"act":' .. jq(fleet.act or ""), '"f":' .. face, '"n":' .. fleet.n, '"total":' .. fleet.total,
    '"done":' .. (fleet.done and "true" or "false"), '"run":' .. fleet.run }, ",")
  local fix = gpsFix(now)
  if fix then body = body .. ',"gps":[' .. fix[1] .. "," .. fix[2] .. "," .. fix[3] .. "]" end
  if fleet.extra then                                          -- a program may add fields (the Foreman: inventory and crafting queue)
    local okx, frag = pcall(fleet.extra)
    if okx and type(frag) == "string" then body = body .. frag end
  -- v8.0: every turtle reports what it carries (slot, item, count) and whether it can craft, for the Inventory tab. Rate-limited: 16 inventory calls per report is not free.
  elseif turtle and turtle.getItemDetail and (force or now - (fleet.invAt or -100) > 8) then      -- everybody else: what I carry (the Fleet page's inventory tab)
    fleet.invAt = now
    local inv = {}
    for sl = 1, 16 do
      local d = turtle.getItemDetail(sl)
      if d and d.name then inv[#inv + 1] = "[" .. sl .. "," .. jq(d.name) .. "," .. (d.count or 0) .. "]" end
    end
    body = body .. ',"crafty":' .. (turtle.craft and "true" or "false") .. ',"inv":[' .. table.concat(inv, ",") .. "]"
  end
  body = body .. "}"
  local ok, res, err = pcall(http.post, { url = LIVE_URL .. "/status", body = body, timeout = 5,
                                          headers = { ["Content-Type"] = "application/json" } })
  if ok and res then
    fleet.fails = 0
    fleet.status = "reporting OK to " .. LIVE_URL
    local reply = ""
    pcall(function() reply = res.readAll() or ""; res.close() end)
    handleReply(reply)
    mapFlush(false)
  else
    fleet.fails = fleet.fails + 1
    local why = tostring(ok and err or res or "no answer"):gsub("%s+", " ")
    fleet.status = "NOT reaching " .. LIVE_URL .. ": " .. why
    if fleet.fails >= 5 then fleet.retryAt = os.clock() + 30 end            -- keep trying every 30 s: the app may simply not be listening yet
  end
end

local function say(...)
  local lines = { ... }
  term.setBackgroundColor(colors.black)
  term.setTextColor(colors.white)
  term.clear()
  for i, l in ipairs(lines) do
    term.setCursorPos(1, i)
    term.write(tostring(l))
  end
  local parts = {}
  for i = 2, #lines do
    if tostring(lines[i]) ~= "" then parts[#parts + 1] = tostring(lines[i]) end
  end
  fleet.msg = table.concat(parts, " ")
  fleet.act = ""                                               -- a new screen: the old "trying to ..." is stale
  fleetSend(false)
  local w, h = term.getSize()
  if fleet.status ~= "" and h > #lines + 1 then
    term.setCursorPos(1, h)
    term.write(("App: " .. fleet.status):sub(1, w))
  end
  if fleet.world and #lines + 3 <= h - 1 then
    term.setCursorPos(1, #lines + 2)
    term.write("World " .. fleet.world[1] .. " " .. fleet.world[2] .. " " .. fleet.world[3])
    local n = fleet.peers[1]
    if n then
      local d = math.abs(n.x - fleet.world[1]) + math.abs(n.y - fleet.world[2]) + math.abs(n.z - fleet.world[3])
      term.setCursorPos(1, #lines + 3)
      term.write("Nearest " .. n.name .. " " .. d .. " blocks")
    end
  end
end

-- the last screen of a program: shown, reported as finished
local function finish(...)
  fleet.done = true
  say(...)
  mapFlush(true)
  fleetSend(true)
end

-- run the program's main(); report errors / Ctrl+T / a Fleet "stop" before ending
local function runMain(main)
  if fleet.on then writeFile("carve.live", LIVE_URL) end       -- so "carve start <id> <program>" knows where the app is
  fleetSend(true)
  local ok, err = pcall(main)
  if not ok then
    if fleet.stopAsked and tostring(err):find("Terminated") then      -- Stop on the Fleet page really stops: no automatic restart afterwards
      pcall(removeStartup); if STATE_FILE then pcall(fs.delete, STATE_FILE) end
      fleet.msg = "Stopped from the Fleet page. It will not restart by itself."
    else
      fleet.msg = tostring(err):find("Terminated") and "Stopped (resumes with: carve resume)" or ("Error: " .. tostring(err))
    end
    fleetSend(true)
    error(err, 0)
  end
end

local function itemName(slot)
  local it = turtle.getItemDetail(slot)
  return it and it.name or nil
end

local function has(name, pattern)
  return name ~= nil and name:find(pattern, 1, true) ~= nil
end

-- chests (and furnaces) a turtle carries are building material: never dumped into a chest
local function isChestItem(n) return n ~= nil and (n:find("chest", 1, true) ~= nil or n:find("barrel", 1, true) ~= nil) end
local function isBuildItem(n) return isChestItem(n) or n == "minecraft:furnace" end

local PROTECTED = { "furnace", "chest", "barrel", "hopper", "crafting_table", "shulker", "smoker" }
local function isProtected(data)
  local n = type(data) == "table" and data.name or ""
  for _, w in ipairs(PROTECTED) do
    if n:find(w, 1, true) then return true end
  end
  return false
end

-- burn items whose name contains one of BURN (a list) until the turtle has `target` fuel
-- v8.2: charcoal is burned before coal. Charcoal is made from logs by the smelter, so coal is kept for when nothing else is left.
local function burn(target)
  local lvl = turtle.getFuelLevel()
  if lvl == "unlimited" then return end
  target = math.min(target, turtle.getFuelLimit())
  local words = { "charcoal" }                                -- charcoal first: it is made from logs, so coal is saved for when it is needed
  for _, w in ipairs(BURN) do if w ~= "charcoal" then words[#words + 1] = w end end
  for _, w in ipairs(words) do
    for s = 1, 16 do
      if turtle.getFuelLevel() >= target then break end
      local n = itemName(s)
      if n and n:find(w, 1, true) and not (KEEP and KEEP[s]) then
        turtle.select(s)
        while turtle.getItemCount(s) > 0 and turtle.getFuelLevel() < target do
          if not turtle.refuel(1) then break end
        end
      end
    end
  end
  turtle.select(1)
end

local function ensureFuel()
  local lvl = turtle.getFuelLevel()
  if lvl == "unlimited" or lvl > 150 then return end
  act("refuelling")
  burn(600)
  while turtle.getFuelLevel() ~= "unlimited" and turtle.getFuelLevel() < 5 do
    say(TITLE, "", "Out of fuel! Put " .. FUEL_HINT, "in my inventory.")
    sleep(5)
    burn(600)
  end
end

local function turnTo(f)
  local diff = (f - face) % 4
  if diff == 3 then
    turtle.turnLeft()
    face = (face + 2) % 4 + 1
    savePos()
  else
    for _ = 1, diff do
      turtle.turnRight()
      face = face % 4 + 1
      savePos()
    end
  end
end

-- move one cell in direction d (digging leaves/dirt out of the way, never furnaces or chests)
local function step(d)
  ensureFuel()
  local detect, dig, inspect, attack, move
  if d == 5 then
    detect, dig, inspect, attack, move = turtle.detectUp, turtle.digUp, turtle.inspectUp, turtle.attackUp, turtle.up
  elseif d == 6 then
    detect, dig, inspect, attack, move = turtle.detectDown, turtle.digDown, turtle.inspectDown, turtle.attackDown, turtle.down
  else
    turnTo(d)
    detect, dig, inspect, attack, move = turtle.detect, turtle.dig, turtle.inspect, turtle.attack, turtle.forward
  end
  local tries = 0
  while true do
    local ok, err = move()
    if ok then
      pos.x, pos.y, pos.z = pos.x + DX[d], pos.y + DY[d], pos.z + DZ[d]
      savePos()
      mapSee()
      fleetSend(false)                                         -- keeps the position on the Fleet map moving
      return
    end
    tries = tries + 1
    if err and tostring(err):lower():find("fuel") then
      ensureFuel()
      sleep(1)
    elseif detect() then
      local _, data = inspect()
      if isProtected(data) then
        say(TITLE, "", "Blocked by " .. tostring(data.name), "Clear the way. Waiting...")
        act("blocked by " .. tostring(data.name):gsub("^minecraft:", "") .. ", waiting for it to be cleared")
        fleetSend(true)
        sleep(3)
      else
        act("digging through " .. tostring(type(data) == "table" and data.name or "a block"):gsub("^minecraft:", ""))
        dig()
      end
    else
      act("something is in my way, attacking it")
      attack()
      sleep(0.4)
    end
    if tries % 25 == 0 then sleep(2) end
  end
end

-- go to (x, y, z), moving along the axes in the order given, e.g. "yzx"
local function goTo(x, y, z, order)
  act("walking to " .. x .. ", " .. y .. ", " .. z)
  for c in (order or "yzx"):gmatch(".") do
    if c == "y" then
      while pos.y < y do step(5) end
      while pos.y > y do step(6) end
    elseif c == "z" then
      while pos.z < z do step(1) end
      while pos.z > z do step(3) end
    else
      while pos.x < x do step(2) end
      while pos.x > x do step(4) end
    end
  end
end

local function freeSlots()
  local n = 0
  for s = 1, 16 do
    if turtle.getItemCount(s) == 0 then n = n + 1 end
  end
  return n
end

-- drop everything except the slots in `keep` (a set) into whatever container is in front
local function dumpFront(keep)
  for s = 1, 16 do
    if turtle.getItemCount(s) > 0 and not (keep and keep[s]) and not isBuildItem(itemName(s)) then
      turtle.select(s)
      turtle.drop()
    end
  end
  turtle.select(1)
end

local function waitSeconds(total, label)
  act("waiting: " .. tostring(label))
  local left = total
  while left > 0 do
    say(TITLE, "", label, "Next check in " .. math.ceil(left) .. "s", "Ctrl+T stops (resumable).")
    local chunk = math.min(5, left)
    sleep(chunk)
    left = left - chunk
  end
end

-- make sure there is a chest in the neighbouring cell in direction d (1-4), placing one from my inventory if the
-- cell is empty. Waits until somebody gives me a chest.
local function ensureChest(d, label)
  act("making sure there is a chest for the " .. tostring(label))
  turnTo(d)
  local ok, data = turtle.inspect()
  if ok then
    if isChestItem(type(data) == "table" and data.name or nil) then return true end
    if isProtected(data) then return false end              -- a furnace or something else I must not break
    turtle.dig()                                           -- earth or stone where the chest goes: dig it out, then place the chest
  end
  while true do
    for s = 1, 16 do
      if isChestItem(itemName(s)) then
        turtle.select(s)
        local placed = turtle.place()
        turtle.select(1)
        if placed then return true end
      end
    end
    say(TITLE, "", "I need a chest for the " .. label .. ".", "Put one in my inventory", "(slot 1). Waiting...")
    sleep(5)
  end
end

-- one move without digging; false when something is in the way
local function tryMove(d)
  if d <= 4 then turnTo(d) end
  ensureFuel()
  local fn = d == 5 and turtle.up or d == 6 and turtle.down or turtle.forward
  if fn() then
    pos.x, pos.y, pos.z = pos.x + DX[d], pos.y + DY[d], pos.z + DZ[d]
    savePos()
    mapSee()
    fleetSend(false)
    return true
  end
  return false
end

-- walk to (x, y, z) in this turtle's own frame, climbing over whatever is in the way; false if it can't
local function travelTo(x, y, z)
  act("travelling to " .. x .. ", " .. y .. ", " .. z)
  for _ = 1, 3000 do
    if pos.x == x and pos.y == y and pos.z == z then return true end
    local d = pos.x < x and 2 or pos.x > x and 4 or pos.z < z and 1 or pos.z > z and 3 or nil
    if d then
      if not tryMove(d) then
        local up = 0
        while not tryMove(d) do                                 -- blocked: climb until the way is clear
          if not tryMove(5) then
            local ok, data = turtle.inspectUp()
            if ok and isProtected(data) then return false end
            turtle.digUp()
            if not tryMove(5) then return false end
          end
          up = up + 1
          if up > 40 then return false end
        end
      end
    elseif pos.y > y then
      if not tryMove(6) then return false end
    else
      if not tryMove(5) then return false end
    end
  end
  return false
end
'''
AUTO_TREEFARM_TEMPLATE = r'''-- Carve tree farm: plants saplings on a grid, waits (or uses bone meal), chops the trees,
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
'''
AUTO_SMELTER_TEMPLATE = r'''-- Carve auto smelter: feeds a row of furnaces from an input chest and puts the results in an output chest.
--
-- Layout (top view, you stand on START facing the furnaces, "F" = furnace, it needs free air above and below):
--        F F F F ...        furnaces, 2 blocks in front of the start row
--        . . . . ...        the turtle's walkway (1 block in front)
--      [out] T              T = START, [out] = output chest on its left, [in] = input chest behind it
--            [in]
-- Put raw items AND your fuel (coal) in the input chest. Run with  setup  to let the turtle place the furnaces.
-- It can't dig out furnaces or chests, but it will dig dirt/stone out of its own way (it walks above and below the furnaces).
--
-- VERSION NOTES
--   - 8.2: every pile is split evenly over all furnaces so they run at the same time (allocate); charcoal is the preferred fuel and a
--     reserve of two rounds is kept (KEEP_CHARCOAL), the surplus goes to the output chest and on into storage.

local args = { ... }

--@@PLAN@@

local STATE_FILE = "carve.smelter"
local TITLE = PLAN.name or "Auto smelter"
local FUEL = PLAN.fuel or "minecraft:coal"
local FUEL_HINT = FUEL:gsub("^minecraft:", "")
local BURN = { (FUEL:gsub("^minecraft:", "")), "charcoal" }
local KEEP = {}

--@@COMMON@@

local F = PLAN.furnaces

-- how many items one piece of fuel smelts
local FUEL_ITEMS = { coal = 8, charcoal = 8, coal_block = 80, lava_bucket = 100, blaze_rod = 12,
                     log = 1.5, planks = 1.5, wood = 1.5, stick = 0.5 }
local PER_FUEL = 1.5
do
  local short = FUEL:gsub("^minecraft:", "")
  for k, v in pairs(FUEL_ITEMS) do
    if short:find(k, 1, true) then PER_FUEL = v end
  end
end
local KEEP_FUEL = 64                                   -- how much of my own coal I hold on to
local KEEP_CHARCOAL = math.max(64, F * 16)              -- charcoal kept to run every furnace for two rounds; the rest goes to the output chest (and so into storage)

local CHARCOAL = "minecraft:charcoal"
local SWITCH_AT = 32          -- once I hold this much charcoal I burn that instead of coal or wood
local function isWood(n) return n ~= nil and (n:find("log", 1, true) or n:find("planks", 1, true) or n:find("_wood", 1, true)) ~= nil end
local function isFuelName(n) return n == FUEL or n == CHARCOAL or n == "minecraft:coal" end

local function slotsOf(name)
  local t = {}
  for s = 1, 16 do
    if itemName(s) == name then t[#t + 1] = s end
  end
  return t
end

local function countOf(name)
  local n = 0
  for _, s in ipairs(slotsOf(name)) do n = n + turtle.getItemCount(s) end
  return n
end

local function fuelSlots()
  return slotsOf(FUEL)
end

local function fuelCount()
  return countOf(FUEL)
end

local function perFuel(name)
  local short = (name or ""):gsub("^minecraft:", "")
  local v = 1.5
  for k, x in pairs(FUEL_ITEMS) do
    if short:find(k, 1, true) then v = x end
  end
  return v
end

-- what to burn for `name`: charcoal as soon as I have some (it is made from the logs, so it never runs out), else my coal, else the wood itself
local function chooseFuel(name)
  if name ~= CHARCOAL and countOf(CHARCOAL) > 1 then return CHARCOAL end
  if countOf(FUEL) > 1 then return FUEL end
  if countOf("minecraft:coal") > 1 then return "minecraft:coal" end
  if isWood(name) then return name end                       -- bootstrap: burn some of the logs to make the first charcoal
  for s = 1, 16 do
    if isWood(itemName(s)) then return itemName(s) end
  end
  return nil
end

local function home()
  goTo(pos.x, 0, 1, "y")
  goTo(0, 0, 1, "x")
  goTo(0, 0, 0, "z")
end

-- walk to the walkway cell in front of furnace k (k = 1 .. F) facing the furnace
local function toFurnace(k)
  goTo(k - 1, 0, 1, "yzx")
  turnTo(1)
end

-- take what is in the input chest into my inventory (keeps two slots free)
local function pull()
  turnTo(3)
  local got = false
  for _ = 1, 60 do
    if freeSlots() < 3 then break end
    if not turtle.suck() then break end
    got = true
  end
  return got
end

-- put the smelted items (and anything else that is not on its way to a furnace) in the output chest
local function unload(pending)
  local keep = {}
  for s in pairs(pending or {}) do keep[s] = true end
  for _, spec in ipairs({ { FUEL, KEEP_FUEL }, { CHARCOAL, KEEP_CHARCOAL } }) do      -- fuel I need stays; anything above goes on
    local held = 0
    for _, s in ipairs(slotsOf(spec[1])) do
      if held < spec[2] then keep[s] = true; held = held + turtle.getItemCount(s) end
    end
  end
  turnTo(4)
  dumpFront(keep)
  turnTo(1)
end

-- drop n of item `name` with `fn` (turtle.drop = into the furnace's fuel slot, turtle.dropDown = its input slot); returns how many went in
local function dropN(name, n, fn)
  local gone = 0
  for _, s in ipairs(slotsOf(name)) do
    if gone >= n then break end
    turtle.select(s)
    local before = turtle.getItemCount(s)
    fn(math.min(n - gone, before))
    gone = gone + (before - turtle.getItemCount(s))
  end
  turtle.select(1)
  return gone
end

local fuelNote = ""
-- one furnace gets e.count items of e.name plus the fuel for them
local function feed(k, e)
  toFurnace(k)
  local fuel = chooseFuel(e.name)
  local input = e.count
  if fuel == e.name then                                    -- burning the very logs I am smelting: some of them become the fuel
    local f = math.ceil(e.count * 0.4)
    input = e.count - f
    dropN(e.name, f, turtle.drop)
    fuelNote = "burning logs for fuel"
  elseif fuel then
    local keepOne = (fuel == FUEL or fuel == "minecraft:coal") and 1 or 0     -- one coal for the turtle itself
    dropN(fuel, math.min(math.ceil(e.count / perFuel(fuel)), countOf(fuel) - keepOne), turtle.drop)
    fuelNote = "burning " .. fuel:gsub("^minecraft:", "")
  else
    fuelNote = "no fuel: waiting for logs or coal"
  end
  step(5); step(1)                                          -- above the furnace
  dropN(e.name, input, turtle.dropDown)
  step(3); step(6)
end

-- what I hold to smelt, as totals per kind (biggest pile first)
local function piles()
  local total, order = {}, {}
  for s = 1, 16 do
    local n = itemName(s)
    if n and not isFuelName(n) and not isBuildItem(n) then
      if not total[n] then total[n] = 0; order[#order + 1] = n end
      total[n] = total[n] + turtle.getItemCount(s)
    end
  end
  table.sort(order, function(a, b) return total[a] > total[b] end)
  return total, order
end

-- who gets what: every kind gets a furnace, the spare furnaces go to the biggest piles, and each pile is split evenly over its
-- furnaces so all of them work at the same time (a furnace takes at most one stack)
-- v8.2: before, one stack went into one furnace, so a single big pile of cobblestone used one furnace. Now each kind gets its own furnaces and the
-- spare furnaces share the biggest piles.
local function allocate(total, order)
  local assigned, used = {}, 0
  for _, n in ipairs(order) do
    if used < F then assigned[n] = 1; used = used + 1 end
  end
  while used < F do
    local best, load = nil, 1
    for _, n in ipairs(order) do
      local a = assigned[n]
      if a and a < total[n] and total[n] / a > load then best, load = n, total[n] / a end
    end
    if not best then break end
    assigned[best] = assigned[best] + 1; used = used + 1
  end
  local list = {}
  for _, n in ipairs(order) do
    local a = assigned[n]
    if a then
      local sum = math.min(total[n], a * 64)
      for i = 1, a do list[#list + 1] = { name = n, count = math.floor(sum / a) + (i <= sum % a and 1 or 0) } end
    end
  end
  return list
end

local function collect(k)
  toFurnace(k)
  step(6); step(1)                                  -- below the furnace
  local n = 0
  while turtle.suckUp() do
    n = n + 1
    if n > 10 or freeSlots() < 1 then break end
  end
  step(3); step(5)
end

local function furnaceSlot()
  for s = 1, 16 do
    if itemName(s) == "minecraft:furnace" then return s end
  end
end

-- place the missing furnaces (and the two chests). With waitForItems it waits until somebody hands me the furnaces.
local function setup(waitForItems)
  ensureChest(3, "raw items")
  ensureChest(4, "results")
  turnTo(1)
  for k = 1, F do
    toFurnace(k)
    local ok, data = turtle.inspect()
    if not (ok and has(data.name, "furnace")) then
      if ok then turtle.dig() end
      local s = furnaceSlot()
      while not s do
        if not waitForItems then
          say(TITLE, "", "Put " .. F .. " furnaces in my inventory", "(furnace " .. k .. " is missing), then", "run setup again.")
          home(); turnTo(1)
          return false
        end
        say(TITLE, "", "Put furnaces in my inventory", "(furnace " .. k .. "/" .. F .. " is missing). Waiting...")
        sleep(5)
        s = furnaceSlot()
      end
      turtle.select(s)
      turtle.place()
    end
  end
  turtle.select(1)
  home(); turnTo(1)
  return true
end

local function recover()
  if pos.y ~= 0 then goTo(pos.x, 0, pos.z, "y") end
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
  if args[1] == "setup" then
    if setup(false) then
      say(TITLE, "", "Furnaces and chests are in place.", "Chest BEHIND me = input,", "chest on my LEFT = output.", "Run me again without setup.")
    end
    return
  end
  installStartup()
  setup(true)                                        -- builds whatever is missing: chests from my inventory, furnaces
  local idle, stuck = 0, 0
  while true do
    pull()
    local total, order = piles()
    if #order == 0 then
      turnTo(1)
      idle = idle + 1
      if PLAN.once then break end
      waitSeconds(30, "Nothing to smelt. Waiting for items.")
    else
      idle = 0
      local list = allocate(total, order)
      local before, longest = 0, 0
      for _, e in ipairs(list) do longest = math.max(longest, e.count) end
      for _, n in ipairs(order) do before = before + total[n] end
      for i, e in ipairs(list) do
        say(TITLE, "", "Loading furnace " .. i .. "/" .. #list, "Items " .. e.count .. " x " .. e.name:gsub("^minecraft:", ""),
            fuelNote ~= "" and fuelNote or ("charcoal " .. countOf(CHARCOAL) .. "/" .. KEEP_CHARCOAL))
        feed(i, e)
      end
      home()
      waitSeconds(longest * 10 + 6, "Smelting in " .. #list .. " furnace(s)...")
      for i = 1, #list do collect(i) end
      home()
      -- what is left of the kinds I loaded stays in me for the next round; the products and the rest go to the output chest
      local pending, left = {}, 0
      for s = 1, 16 do
        local n = itemName(s)
        if n and total[n] then pending[s] = true; left = left + turtle.getItemCount(s) end
      end
      stuck = left < before and 0 or stuck + 1
      if stuck >= 2 then
        say(TITLE, "", "Some items won't go into the", "furnaces (not smeltable?).", "Putting them in the output chest.")
        pending = {}
        stuck = 0
      end
      unload(pending)
    end
  end
  removeStartup()
  fs.delete(STATE_FILE)
  finish(TITLE, "", "All done. Output is in the chest.")
end

if rawget(_G, "CARVE_TEST") then
  return { main = main, pos = pos }
end
runMain(main)
'''
AUTO_CRAFTER_TEMPLATE = r'''-- Carve auto crafter: crafts one recipe over and over from an input chest into an output chest.
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
'''
AUTO_SCOUT_TEMPLATE = r'''-- Carve scout: walks (and flies) through open space, looks at every block around it and reports what it
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
'''
AUTO_AGENT_TEMPLATE = r'''-- Carve agent: an idle turtle that waits for orders. Start a program on it from the Designer's Fleet tab,
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
'''
AUTO_MINER_TEMPLATE = r'''-- Carve miner: goes underground and looks for resources (coal, iron, copper, gold, redstone, lapis, diamond, emerald).
-- It digs a shaft straight down from the START cell, then a tunnel (the spine) and side tunnels (ribs) every 3 blocks,
-- checks every wall it passes, and mines any wanted ore it sees (following the whole vein). When its inventory is
-- full it climbs back, empties itself into the chest BEHIND the start, and returns. Coal it finds refuels it.
-- Stand on the START cell facing forward (+z); put a chest right behind you; give it some coal to start.
-- Run again with  stop  to cancel the automatic restart.

local args = { ... }

--@@PLAN@@

local STATE_FILE = "carve.miner"
local PROG_FILE = "carve.minerprog"
local TITLE = PLAN.name or "Miner"
local FUEL_HINT = "coal"
local BURN = { "coal", "charcoal" }

--@@COMMON@@

local DEPTH, REACH, RIB = PLAN.depth, PLAN.reach, PLAN.rib
local OPP = { 3, 4, 1, 2, 6, 5 }
local JUNK = { "cobblestone", "cobbled_deepslate", "dirt", "gravel", "andesite", "diorite", "granite", "tuff",
               "netherrack", "sand", "stone", "deepslate", "calcite", "dripstone" }
local found, nribs = 0, 0
local spineLen, ribsDone = 0, 0
local outbox, lastFlush = {}, 0

local function wanted(name)
  if not name or not name:find("_ore", 1, true) then return false end
  for _, w in ipairs(PLAN.want) do
    if name:find(w, 1, true) then return true end
  end
  return false
end

local function liquid(name)
  return name ~= nil and (name:find("lava", 1, true) ~= nil or name:find("water", 1, true) ~= nil)
end

local function flush(force)
  if not fleet.on then outbox = {}; return end
  if #outbox == 0 or (not force and #outbox < 20 and os.clock() - lastFlush < 60) then return end
  lastFlush = os.clock()
  local parts = {}
  for _, c in ipairs(outbox) do
    parts[#parts + 1] = "[" .. c[1] .. "," .. c[2] .. "," .. c[3] .. "," .. jq(c[4]) .. "]"
  end
  outbox = {}
  pcall(http.post, { url = LIVE_URL .. "/map", timeout = 5, headers = { ["Content-Type"] = "application/json" },
    body = '{"v":1,"id":' .. os.getComputerID() .. ',"cells":[' .. table.concat(parts, ",") .. "]}" })
end

local function inspectDir(d)
  local ok, data
  if d == 5 then ok, data = turtle.inspectUp()
  elseif d == 6 then ok, data = turtle.inspectDown()
  else turnTo(d); ok, data = turtle.inspect() end
  if not ok then return nil end
  return type(data) == "table" and (data.name or "?") or "?"
end

local function digDir(d)
  if d == 5 then return turtle.digUp() elseif d == 6 then return turtle.digDown() end
  turnTo(d)
  return turtle.dig()
end

-- throw away stone and dirt when the inventory is getting full
local function dropJunk()
  for s = 1, 16 do
    local n = itemName(s)
    if n then
      for _, j in ipairs(JUNK) do
        if n == "minecraft:" .. j then
          turtle.select(s)
          turtle.dropDown()
          break
        end
      end
    end
  end
  turtle.select(1)
end

-- empty the inventory into the chest behind the start, then come back to where we were
local function unloadTrip()
  local bx, by, bz = pos.x, pos.y, pos.z
  goTo(0, by, 0, "zx")
  goTo(0, 0, 0, "y")
  burn(1500)
  turnTo(3)
  while true do
    dumpFront()
    if freeSlots() >= 14 then break end
    say(TITLE, "", "The chest behind me is full.", "Empty it. Waiting...")
    sleep(10)
  end
  turnTo(1)
  fleet.msg = "Unloaded"
  goTo(0, by, 0, "y")
  goTo(bx, by, bz, "xz")
end

local function checkSpace()
  if freeSlots() <= 4 then dropJunk() end
  if freeSlots() <= 2 then unloadTrip() end
end

-- mine the ore I am looking at and everything of the same kind touching it
local function vein(budget)
  local order = { 5, 6, face, face % 4 + 1, (face + 1) % 4 + 1, (face + 2) % 4 + 1 }
  for _, d in ipairs(order) do
    if budget <= 0 then break end
    local name = inspectDir(d)
    if wanted(name) then
      outbox[#outbox + 1] = { pos.x + DX[d], pos.y + DY[d], pos.z + DZ[d], name }
      digDir(d)
      found = found + 1
      fleet.n = found
      step(d)
      budget = vein(budget - 1)
      step(OPP[d])
    end
  end
  return budget
end

local function lookAround()
  vein(40)
  checkSpace()
end

-- dig one cell along direction d and step into it; false when something stops us (liquid, bedrock)
local function tunnelStep(d)
  local name = inspectDir(d)
  if liquid(name) or name == "minecraft:bedrock" then return false end
  step(d)
  return true
end

local function saveProgress()
  writeFile(PROG_FILE, ribsDone .. "," .. spineLen)
end

local function loadProgress()
  local s = readFile(PROG_FILE)
  local a, b = (s or ""):match("^(%d+),(%d+)")
  if a then ribsDone, spineLen = tonumber(a), tonumber(b) end
end

local function status(what)
  fleet.total = nribs
  say(TITLE, "", what, "Rib " .. ribsDone .. "/" .. nribs .. "  ores found " .. found,
      "At " .. pos.x .. " " .. pos.y .. " " .. pos.z)
end

-- dig the shaft straight down from the start
local function shaft()
  while pos.y > -DEPTH do
    if not tunnelStep(6) then break end
    lookAround()
    if pos.y % 5 == 0 then status("Going down...") end
  end
end

-- extend the main tunnel (east) up to x, looking at the walls as it goes
local function spineTo(x)
  goTo(spineLen, -DEPTH, 0, "yxz")
  while spineLen < x do
    if not tunnelStep(2) then spineLen = x; break end     -- blocked: ribs beyond are skipped
    spineLen = spineLen + 1
    lookAround()
  end
  saveProgress()
end

local function rib(k)
  local i, side = math.ceil(k / 2), (k % 2 == 1) and 1 or -1
  local x = 3 * i
  spineTo(x)
  goTo(x, -DEPTH, 0, "yxz")
  local d = side > 0 and 1 or 3
  for _ = 1, RIB do
    if not tunnelStep(d) then break end
    lookAround()
  end
  goTo(x, -DEPTH, 0, "z")
  ribsDone = k
  saveProgress()
  flush(true)
  status("Mining...")
end

local function main()
  if not turtle then printError("This program must run on a turtle."); return end
  if args[1] == "stop" then
    removeStartup(); fs.delete(STATE_FILE); fs.delete(PROG_FILE)
    finish(TITLE, "", "Stopped. The automatic restart is removed.")
    return
  end
  nribs = math.floor(REACH / 3) * 2
  if RIB == 0 then nribs = 0 end
  if args[1] == "resume" and loadPos() then
    say(TITLE, "", "Resuming after a restart...")
    loadProgress()
    goTo(0, pos.y, 0, "zx")                               -- back along the tunnels to the shaft
    goTo(0, 0, 0, "y")
  else
    fs.delete(STATE_FILE); fs.delete(PROG_FILE)
    pos.x, pos.y, pos.z, face = 0, 0, 0, 1
    savePos()
  end
  installStartup()
  ensureChest(3, "finds"); turnTo(1)
  shaft()
  if RIB == 0 then
    spineTo(REACH)
  else
    for k = ribsDone + 1, nribs do rib(k) end
    spineTo(REACH)
  end
  flush(true)
  goTo(0, -DEPTH, 0, "zx")
  goTo(0, 0, 0, "y")
  burn(1500)
  turnTo(3)
  dumpFront()
  turnTo(1)
  removeStartup()
  fs.delete(STATE_FILE); fs.delete(PROG_FILE)
  finish(TITLE, "", "Done. " .. found .. " ores mined.", "Everything is in the chest.")
end

if rawget(_G, "CARVE_TEST") then
  return { main = main, pos = pos }
end
runMain(main)
'''
AUTO_HAULER_TEMPLATE = r'''-- Carve hauler: carries items between the chests of your other jobs. Each leg says where to take items from
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
'''
AUTO_KEEPER_TEMPLATE = r'''-- Carve storage keeper: a warehouse of chests that builds itself, remembers what is in every chest and
-- reports the list to the Designer app (Storage tab of the Fleet page).
--
--   behind the start : the DROP chest. Anything put in there (by you or by a hauler) is sorted into storage.
--   left of the start: the PICKUP chest. Items you ask for on the web page are put there.
--   in front         : a corridor with up to 4 storage chests per step (right, left, above, below).
--
-- Start it with a chest in the first slot (more chests, fuel in other slots). It places the drop chest, the
-- pickup chest and then one storage chest at a time when it needs room. Chests dropped into the drop chest
-- are kept by the turtle and used to grow the warehouse.
-- Run again with  stop  to cancel the automatic restart;  reset  forgets the list of what is stored.

local args = { ... }

--@@PLAN@@

local STATE_FILE = "carve.keeper"
local INDEX_FILE = "carve.keeperidx"
local TITLE = PLAN.name or "Storage keeper"
local FUEL_HINT = "coal or charcoal"
local BURN = { "coal", "charcoal" }
local KEEP = {}

--@@COMMON@@

local MAXC = PLAN.length * 4            -- most storage chests this warehouse may grow to
local STACKMAX = 64
local built = 0                         -- storage chests placed so far
local idx = {}                          -- idx[k] = { [item name] = count }  for chest k
local full = {}                         -- full[k] = true while chest k refused items
local orders = {}                       -- { { item =, count = } } waiting to be put in the pickup chest
local reported = -100
local hasPeripheral = peripheral ~= nil and peripheral.wrap ~= nil
local dirty = true

local SIDES = {
  { name = "right", face = 2, drop = "drop", suck = "suck", wrap = "front" },
  { name = "left", face = 4, drop = "drop", suck = "suck", wrap = "front" },
  { name = "above", face = nil, drop = "dropUp", suck = "suckUp", wrap = "top" },
  { name = "below", face = nil, drop = "dropDown", suck = "suckDown", wrap = "bottom" },
}

local function cellOf(k) return math.floor((k - 1) / 4) + 1 end
local function sideOf(k) return SIDES[(k - 1) % 4 + 1] end

---------------------------------------------------------------- the list of what is stored
local function saveIndex()
  local out = { "built " .. built }
  for k = 1, built do
    for name, c in pairs(idx[k] or {}) do
      if c > 0 then out[#out + 1] = k .. " " .. c .. " " .. name end
    end
  end
  writeFile(INDEX_FILE, table.concat(out, "\n") .. "\n")
  dirty = true
end

local function loadIndex()
  local s = readFile(INDEX_FILE)
  if not s then return end
  built = 0
  for line in s:gmatch("[^\n]+") do
    local b = line:match("^built (%d+)$")
    if b then
      built = tonumber(b)
      for k = 1, built do idx[k] = idx[k] or {} end
    else
      local k, c, name = line:match("^(%d+) (%d+) (.+)$")
      k = tonumber(k)
      if k and k <= built then idx[k][name] = tonumber(c) end
    end
  end
end

local function totals()
  local t, stacks = {}, 0
  for k = 1, built do
    for name, c in pairs(idx[k] or {}) do
      t[name] = (t[name] or 0) + c
      stacks = stacks + math.ceil(c / STACKMAX)
    end
  end
  return t, stacks
end

local function emptyChests()
  local n = 0
  for k = 1, built do
    if next(idx[k]) == nil and not full[k] then n = n + 1 end
  end
  return n
end

---------------------------------------------------------------- talking to the app
local function chestsHeld()
  local n = 0
  for s = 1, 16 do
    if isChestItem(itemName(s)) then n = n + turtle.getItemCount(s) end
  end
  return n
end

-- send the list, get the orders back ("order <count> <item>" lines)
local function sync(force)
  if not fleet.on then return end
  local now = os.clock()
  if not force and not dirty and now - reported < 20 then return end
  if not force and now - reported < 4 then return end
  reported = now
  local t, stacks = totals()
  local parts = {}
  for name, c in pairs(t) do
    if c > 0 then parts[#parts + 1] = jq(name) .. ":" .. c end
  end
  table.sort(parts)
  local body = '{"v":1,"id":' .. os.getComputerID() .. ',"name":' .. jq(PLAN.name or "") ..
    ',"chests":' .. built .. ',"max":' .. MAXC .. ',"stacks":' .. stacks .. ',"slots":' .. (built * 27) ..
    ',"spare":' .. chestsHeld() .. ',"items":{' .. table.concat(parts, ",") .. "}}"
  local ok, res = pcall(http.post, { url = LIVE_URL .. "/storage", body = body, timeout = 5,
                                     headers = { ["Content-Type"] = "application/json" } })
  if not ok or not res then return end
  dirty = false
  local text = ""
  pcall(function() text = res.readAll() or ""; res.close() end)
  for line in text:gmatch("[^\n]+") do
    local n, item = line:match("^order (%d+) ([%w_:%.%-]+)$")
    if n and #orders < 40 then orders[#orders + 1] = { item = item, count = math.min(tonumber(n), 4096) } end
  end
end

local function status(...)
  fleet.n = built
  fleet.total = MAXC
  say(TITLE, "", ...)
  sync(false)
end

---------------------------------------------------------------- walking the corridor
local function toCell(z)
  if pos.x ~= 0 or pos.y ~= 0 then goTo(0, 0, pos.z, "yx") end
  goTo(0, 0, z, "yzx")
end

-- turn to / get ready for a chest at storage position k (or the special "pickup" / "drop" chests)
local function aim(side)
  if side.face then turnTo(side.face) end
end

local function call(side, which, ...)
  if which == "drop" then return turtle[side.drop](...) end
  return turtle[side.suck](...)
end

-- what the chest in front says it holds (needs the peripheral API); nil when it can't be asked
local function peek(side)
  if not hasPeripheral then return nil end
  local ok, p = pcall(peripheral.wrap, side.wrap)
  if not ok or type(p) ~= "table" or not p.list then return nil end
  local ok2, list = pcall(p.list)
  if not ok2 or type(list) ~= "table" then return nil end
  local out = {}
  for _, st in pairs(list) do
    if st and st.name then out[st.name] = (out[st.name] or 0) + (st.count or 0) end
  end
  return out
end

local function refresh(k, side)
  local now = peek(side)
  if now then idx[k] = now end
end

-- is there already a chest in the cell in front / above / below?
local function chestThere(side)
  local fn = side.drop == "dropUp" and turtle.inspectUp or side.drop == "dropDown" and turtle.inspectDown or turtle.inspect
  local ok, data = fn()
  return ok and isChestItem(type(data) == "table" and data.name or nil)
end

-- dig whatever is in the cell, throwing the rubble away so it doesn't fill my inventory
local function clearCell(side)
  local before = {}
  for s = 1, 16 do before[s] = { itemName(s), turtle.getItemCount(s) } end
  local detect = side.drop == "dropUp" and turtle.detectUp or side.drop == "dropDown" and turtle.detectDown or turtle.detect
  local inspect = side.drop == "dropUp" and turtle.inspectUp or side.drop == "dropDown" and turtle.inspectDown or turtle.inspect
  local dig = side.drop == "dropUp" and turtle.digUp or side.drop == "dropDown" and turtle.digDown or turtle.dig
  if detect() then
    local _, data = inspect()
    if isProtected(data) then return false end
    dig()
  end
  for s = 1, 16 do
    local n = itemName(s)
    local c = turtle.getItemCount(s)
    local b = before[s]
    local added = (b[1] == n or b[1] == nil) and (c - (b[1] == n and b[2] or 0)) or 0
    if n and added > 0 and not isChestItem(n) then
      turtle.select(s)
      turtle[side.drop](added)
    end
  end
  turtle.select(1)
  return true
end

local function placeChest(side)
  for s = 1, 16 do
    if isChestItem(itemName(s)) then
      turtle.select(s)
      local fn = side.drop == "dropUp" and turtle.placeUp or side.drop == "dropDown" and turtle.placeDown or turtle.place
      local ok = fn()
      turtle.select(1)
      return ok
    end
  end
  return false
end

-- build storage chest number built+1 if I have a chest and there is room in the plan
local function buildNext()
  if built >= MAXC or chestsHeld() == 0 then return false end
  local k = built + 1
  toCell(cellOf(k))
  local side = sideOf(k)
  aim(side)
  if not chestThere(side) then
    if not clearCell(side) or not placeChest(side) then return false end
  end
  built = k
  idx[k] = {}
  full[k] = nil
  saveIndex()
  status("Built storage chest " .. built .. " of " .. MAXC)
  return true
end

---------------------------------------------------------------- putting things away
local function dropInto(k, s)
  local side = sideOf(k)
  toCell(cellOf(k))
  aim(side)
  turtle.select(s)
  local name = itemName(s)
  local before = turtle.getItemCount(s)
  local ok = call(side, "drop")
  local moved = before - turtle.getItemCount(s)
  turtle.select(1)
  if moved > 0 then
    idx[k][name] = (idx[k][name] or 0) + moved
  end
  if not ok or turtle.getItemCount(s) > 0 then full[k] = true end
  if hasPeripheral then refresh(k, side) end
  return moved
end

-- phase 1: chests that already hold this item, 2: empty chests, 3: any other chest with room
local function tryChests(s, name, phase)
  for k = 1, built do
    if not full[k] then
      local has = idx[k][name] ~= nil
      local empty = next(idx[k]) == nil
      if (phase == 1 and has) or (phase == 2 and empty) or (phase == 3 and not has and not empty) then
        status("Storing " .. name:gsub("^minecraft:", ""))
        dropInto(k, s)
        if turtle.getItemCount(s) == 0 then return true end
      end
    end
  end
  return false
end

-- put the stack in slot s into storage. false when there is no room (and I couldn't build more)
local function storeSlot(s)
  while turtle.getItemCount(s) > 0 do
    local name = itemName(s)
    if tryChests(s, name, 1) or tryChests(s, name, 2) then break end
    if not buildNext() then                     -- a new kind of item gets its own chest if I can build one
      if tryChests(s, name, 3) then break end
      saveIndex()
      return false
    end
  end
  saveIndex()
  return true
end

-- fuel from what comes in: burn a few coal/charcoal when low
local function topUpFuel(s)
  local n = itemName(s)
  if not n or not (n:find("coal", 1, true) or n:find("charcoal", 1, true)) then return end
  local lvl = turtle.getFuelLevel()
  if lvl ~= "unlimited" and lvl < 1500 then
    turtle.select(s)
    turtle.refuel(math.min(turtle.getItemCount(s), 8))
    turtle.select(1)
  end
end

-- chests are kept to build with (up to 2 stacks); everything else goes into storage
local function storeInventory()
  local keptChests = 0
  local ok = true
  for s = 1, 16 do
    local n = itemName(s)
    if n then
      if isChestItem(n) and keptChests < 2 then
        keptChests = keptChests + 1
      elseif n == "minecraft:furnace" then
        -- never mine
      else
        topUpFuel(s)
        if turtle.getItemCount(s) > 0 and not storeSlot(s) then
          ok = false
        end
      end
    end
  end
  return ok
end

local function intake()
  toCell(0)
  turnTo(3)
  local got = 0
  while turtle.suck() do
    got = got + 1
    if freeSlots() <= 3 then
      storeInventory()
      toCell(0)
      turnTo(3)
    end
    if got > 200 then break end
  end
  turnTo(1)
  return got
end

---------------------------------------------------------------- taking things out
local function countInv(name)
  local c = 0
  for s = 1, 16 do
    if itemName(s) == name then c = c + turtle.getItemCount(s) end
  end
  return c
end

local function takeFromChest(k, name, want)
  local side = sideOf(k)
  toCell(cellOf(k))
  aim(side)
  full[k] = nil
  local before = countInv(name)
  local held = {}
  for s = 1, 16 do held[s] = itemName(s) end
  for _ = 1, 40 do
    if countInv(name) >= want or freeSlots() <= 1 then break end
    if not call(side, "suck") then break end
  end
  -- anything else I pulled out goes straight back
  for s = 1, 16 do
    local n = itemName(s)
    if n and n ~= name and n ~= held[s] and not isChestItem(n) then
      turtle.select(s)
      call(side, "drop")
    end
  end
  turtle.select(1)
  if hasPeripheral and peek(side) then
    refresh(k, side)
  else
    local left = (idx[k][name] or 0) - (countInv(name) - before)
    idx[k][name] = left > 0 and left or nil
  end
end

-- carry what is in my inventory of this item to the pickup chest. Returns how many arrived.
local function deliver(name, want)
  toCell(0)
  turnTo(4)
  local moved = 0
  for s = 1, 16 do
    if itemName(s) == name and moved < want then
      turtle.select(s)
      local before = turtle.getItemCount(s)
      turtle.drop(math.min(before, want - moved))
      moved = moved + before - turtle.getItemCount(s)
    end
  end
  turtle.select(1)
  turnTo(1)
  return moved
end

local function fulfil(order)
  local name, want = order.item, order.count
  status("Fetching " .. want .. " " .. name:gsub("^minecraft:", ""))
  local fetched = 0
  for k = 1, built do
    if (idx[k][name] or 0) > 0 and fetched < want then
      takeFromChest(k, name, want - fetched)
      fetched = countInv(name)
      if freeSlots() <= 1 then break end
    end
  end
  -- never hand out more than asked for: the surplus goes back into storage
  local moved = deliver(name, want)
  if moved == 0 and countInv(name) > 0 then
    status("The pickup chest is full.", "Empty it, then ask again.")
    storeInventory()
    return false
  end
  if countInv(name) > 0 then storeInventory() end
  saveIndex()
  return true
end

---------------------------------------------------------------- full scan of every chest
local function rescan()
  if not hasPeripheral then return end
  for k = 1, built do
    local side = sideOf(k)
    toCell(cellOf(k))
    aim(side)
    refresh(k, side)
    full[k] = nil
  end
  saveIndex()
end

local function main()
  if not turtle then printError("This program must run on a turtle."); return end
  if args[1] == "stop" then
    removeStartup(); fs.delete(STATE_FILE)
    finish(TITLE, "", "Stopped. The automatic restart is removed.")
    return
  end
  if args[1] == "reset" then fs.delete(INDEX_FILE) end
  if args[1] == "resume" and loadPos() then
    say(TITLE, "", "Resuming after a restart...")
  else
    pos.x, pos.y, pos.z, face = 0, 0, 0, 1
    savePos()
  end
  loadIndex()
  installStartup()
  ensureChest(3, "drop chest")
  ensureChest(4, "pickup chest")
  turnTo(1)
  local lastScan = os.clock()
  rescan()
  while true do
    -- 1. things people put in the drop chest
    local got = intake()
    if got > 0 then storeInventory() end
    -- 2. grow when there is no empty chest left for a new kind of item
    if emptyChests() == 0 and built < MAXC and chestsHeld() > 0 then buildNext() end
    -- 3. tell the app, then carry out what it asked for
    sync(true)
    local order = table.remove(orders, 1)
    while order do
      fulfil(order)
      order = table.remove(orders, 1)
      sync(true)
    end
    -- 4. now and then look into every chest, in case somebody changed one by hand
    if PLAN.rescan > 0 and os.clock() - lastScan >= PLAN.rescan then
      rescan()
      lastScan = os.clock()
    end
    toCell(0)
    turnTo(1)
    local t, stacks = totals()
    local kinds = 0
    for _ in pairs(t) do kinds = kinds + 1 end
    status("Waiting for deliveries", kinds .. " kinds, " .. stacks .. " stacks, " .. built .. "/" .. MAXC .. " chests",
           chestsHeld() > 0 and "" or (built >= MAXC and "Warehouse is at its maximum." or "Out of spare chests. Add some."))
    sleep(PLAN.wait)
  end
end

if rawget(_G, "CARVE_TEST") then
  return { main = main, pos = pos }
end
runMain(main)
'''
AUTO_FOREMAN_TEMPLATE = r'''-- Carve foreman: sets up the other turtles of the colony so you only have to start this one.
--
--   1. It asks the Designer app where every job's chests (and furnaces) belong, in this turtle's own frame.
--   2. It walks to each spot, stands on top of it and places a chest or a furnace from its inventory
--      (digging out earth that is in the way; it never breaks chests or furnaces).
--   3. It asks the app to hand each job to the nearest idle Agent turtle, which walks to its site and starts the job.
--
-- Needs: live reporting, its own start position (Fleet tab, Colony tab or GPS), the start position of every job
-- (Colony tab: Lay out), the chests and furnaces listed in the Colony tab in its inventory, and some coal.
-- Run again with  stop  to cancel the automatic restart.
--
-- VERSION NOTES
--   - The Foreman is the only turtle that is made by hand. It crafts every other turtle from a chest of materials, boots it, gives it a kit
--     and sends it to its job site.
--   - Up to 7.5 it carried ingredients between crafts and kept re-crafting what it had just put away (it wasted iron on extra hoppers).
--     7.6 rewrote the build mode: everything lives in the two chests, and every craft empties the turtle, takes EXACTLY the
--     ingredients, crafts and stores the result (craftGrid). need(tag, n) crafts only what is missing and stops after a few failed tries.
--   - Why 'empty first': in this modpack turtle.craft only works when the whole inventory outside the 3x3 grid is empty, and the
--     result lands in slot 16.
--   - Why a hopper (7.4): turtle.drop / place into a disk drive does not insert a floppy here, but a hopper above the drive does.
--   - Why a kit CHEST: turtle.drop into another turtle does not insert here either.
--   - 8.1: job sites are offsets from the Foreman (not typed coordinates).

local args = { ... }

--@@PLAN@@

local STATE_FILE = "carve.foreman"
local TITLE = PLAN.name or "Foreman"
local FUEL_HINT = "coal or charcoal"
local BURN = { "coal", "charcoal" }
local KEEP = {}

--@@COMMON@@

local placed = { chest = 0, furnace = 0 }

local function jobsJson(list)
  local parts = {}
  for i, j in ipairs(list or PLAN.jobs) do
    local foot = "null"
    if j.foot then foot = "[" .. table.concat(j.foot, ",") .. "]" end
    parts[i] = '{"name":' .. jq(j.name) .. ',"slug":' .. jq(j.slug) .. ',"kind":' .. jq(j.kind) ..
      ',"furnaces":' .. (j.furnaces or 0) .. ',"foot":' .. foot .. "}"
  end
  return "[" .. table.concat(parts, ",") .. "]"
end

-- one question to the app; returns the lines of the answer, or nil and a reason
-- list = the jobs to send along (default: all of them), extra = more JSON fields like ',"turtle":12'
local function ask(action, list, extra)
  local ok, res = pcall(http.post, { url = LIVE_URL .. "/setup", timeout = 15, headers = { ["Content-Type"] = "application/json" },
    body = '{"v":1,"id":' .. os.getComputerID() .. ',"action":' .. jq(action) .. ',"jobs":' .. jobsJson(list) .. (extra or "") .. "}" })
  if not ok or not res then return nil, "Can't reach the app" end
  local text = ""
  pcall(function() text = res.readAll() or ""; res.close() end)
  local lines = {}
  for line in text:gmatch("[^\n]+") do lines[#lines + 1] = line end
  return lines
end

local function slotOf(what)
  for s = 1, 16 do
    local n = itemName(s)
    if what == "chest" and isChestItem(n) then return s end
    if what == "furnace" and n == "minecraft:furnace" then return s end
  end
end

-- standing above the target cell: put a chest / furnace in it
local function placeHere(what, label)
  local ok, data = turtle.inspectDown()
  if ok then
    local n = type(data) == "table" and data.name or ""
    if (what == "chest" and isChestItem(n)) or (what == "furnace" and n:find("furnace", 1, true)) then return true end   -- already there
    if isProtected(data) then return false end
    turtle.digDown()                                        -- earth or stone: dig it out first
  end
  while true do
    local s = slotOf(what)
    if s then
      turtle.select(s)
      local done = turtle.placeDown()
      turtle.select(1)
      if done then placed[what] = placed[what] + 1; return true end
      return false
    end
    say(TITLE, "", "I need a " .. what .. " for " .. label .. ".", "Put one in my inventory.", "Waiting...")
    sleep(5)
  end
end


-------------------------------------------------------------- build mode: craft the other turtles
-- Layout: the supply chest is BEHIND me (the materials), a sorting chest on my LEFT, the new turtle goes in FRONT of me
-- and a disk drive above it (its floppy holds the first-start program).
local GRID = { 1, 2, 3, 5, 6, 7, 9, 10, 11 }
local RESULT = 16
local function ends(n, suf) return n:sub(-#suf) == suf end
local TAG = {
  log = function(n) return ends(n, "_log") end,
  planks = function(n) return ends(n, "_planks") end,
  stone = function(n) return n == "minecraft:stone" end,
  cobble = function(n) return n == "minecraft:cobblestone" end,
  iron = function(n) return n == "minecraft:iron_ingot" end,
  redstone = function(n) return n == "minecraft:redstone" end,
  glass = function(n) return n == "minecraft:glass" end,
  pane = function(n) return n == "minecraft:glass_pane" end,
  diamond = function(n) return n == "minecraft:diamond" end,
  stick = function(n) return n == "minecraft:stick" end,
  cane = function(n) return n == "minecraft:sugar_cane" end,
  paper = function(n) return n == "minecraft:paper" end,
  coal = function(n) return n == "minecraft:coal" or n == "minecraft:charcoal" end,
  sapling = function(n) return n:find("sapling", 1, true) ~= nil end,
  chest = function(n) return n == "minecraft:chest" end,
  furnace = function(n) return n == "minecraft:furnace" end,
  computer = function(n) return n == "computercraft:computer_normal" end,
  turtle = function(n) return n == "computercraft:turtle_normal" end,
  pickaxe = function(n) return n == "minecraft:diamond_pickaxe" end,
  ctable = function(n) return n == "minecraft:crafting_table" end,
  drive = function(n) return n == "computercraft:disk_drive" end,
  disk = function(n) return n == "computercraft:disk" or (n:find("floppy", 1, true) ~= nil) end,
  hopper = function(n) return n == "minecraft:hopper" end,
  bonemeal = function(n) return n == "minecraft:bone_meal" end,
}
-- recipes: three rows of three tags ("-" = empty). supply = a ready-made one may be waiting in the chest
local R = {
  planks = { rows = { "log - -", "- - -", "- - -" }, supply = true },
  stick = { rows = { "planks - -", "planks - -", "- - -" } },
  chest = { rows = { "planks planks planks", "planks - planks", "planks planks planks" }, supply = true },
  pane = { rows = { "glass glass glass", "glass glass glass", "- - -" }, supply = true },
  computer = { rows = { "stone stone stone", "stone redstone stone", "stone pane stone" } },
  turtle = { rows = { "iron iron iron", "iron computer iron", "iron chest iron" } },
  pickaxe = { rows = { "diamond diamond diamond", "- stick -", "- stick -" } },
  ctable = { rows = { "planks planks -", "planks planks -", "- - -" } },
  furnace = { rows = { "cobble cobble cobble", "cobble - cobble", "cobble cobble cobble" }, supply = true },
  hopper = { rows = { "iron - iron", "iron chest iron", "- iron -" }, supply = true },
  drive = { rows = { "stone stone stone", "stone redstone stone", "stone redstone stone" } },        -- CC: Tweaked: 7 stone and 2 redstone
  paper = { rows = { "cane cane cane", "- - -", "- - -" }, supply = true },
  disk = { rows = { "redstone paper -", "- - -", "- - -" } },
}
local WORDS = { log = "logs", planks = "planks", stone = "stone", cobble = "cobblestone", iron = "iron ingots", redstone = "redstone",
  glass = "glass", pane = "glass panes", diamond = "diamonds", stick = "sticks", cane = "sugar cane", paper = "paper", coal = "coal",
  sapling = "saplings", hopper = "hoppers", chest = "chests", furnace = "furnaces", bonemeal = "bone meal" }

local function count(tag)
  local n = 0
  for s = 1, 16 do
    local nm = itemName(s)
    if nm and TAG[tag](nm) then n = n + turtle.getItemCount(s) end
  end
  return n
end
local function slotOfTag(tag)
  for s = 1, 16 do
    local nm = itemName(s)
    if nm and TAG[tag](nm) then return s end
  end
end
local function snapshot()
  local t = {}
  for s = 1, 16 do
    local nm = itemName(s)
    if nm then t[s] = { name = nm, count = turtle.getItemCount(s) } end
  end
  return t
end

-- what the Fleet page's Foreman tab shows: my inventory and the crafting queue
local crafting, recent, jobQ = {}, {}, {}                      -- tags being crafted (innermost last), finished ones, the turtles still to build
local function pretty(nm) return (tostring(nm or ""):gsub("^%a+:", ""):gsub("_", " ")) end
local function extraJson()
  local inv = {}
  for sl = 1, 16 do
    local nm = turtle.getItemDetail and turtle.getItemDetail(sl)
    nm = nm and nm.name
    if nm then inv[#inv + 1] = "[" .. sl .. "," .. jq(nm) .. "," .. turtle.getItemCount(sl) .. "]" end
  end
  local q = {}
  for i = #crafting, 1, -1 do
    q[#q + 1] = '{"t":' .. jq("Craft " .. pretty(crafting[i])) .. ',"s":"' .. (i == #crafting and "now" or "wait") .. '"}'
  end
  for _, j in ipairs(jobQ) do
    if j.s ~= "done" then q[#q + 1] = '{"t":' .. jq("Turtle for " .. j.name) .. ',"s":"' .. (#crafting == 0 and j.s == "now" and "now" or (j.s == "now" and "wait" or "todo")) .. '"}' end
  end
  for i = #recent, math.max(1, #recent - 5), -1 do
    q[#q + 1] = '{"t":' .. jq("Crafted " .. pretty(recent[i])) .. ',"s":"done"}'
  end
  for _, j in ipairs(jobQ) do
    if j.s == "done" then q[#q + 1] = '{"t":' .. jq("Turtle for " .. j.name) .. ',"s":"done"}' end
  end
  return ',"crafty":true,"inv":[' .. table.concat(inv, ",") .. '],"q":[' .. table.concat(q, ",") .. "]"
end
fleet.extra = extraJson

-- Everything I own lives in two chests: the materials chest BEHIND me (3) and a sorting chest on my LEFT (4).
-- This pack only crafts when the grid holds ALL I carry, so every craft is: empty myself into the chests, take exactly the
-- ingredients, lay them out, craft, put the result into a chest. Nothing is ever carried across a craft.
local STORE = { 4, 8, 12, 13, 14, 15 }                          -- slots outside the crafting grid
local ledger = {}                                                -- [direction] = { item name = count }, from the last look into each chest

local function listChest(d)
  turnTo(d)
  local p = peripheral and peripheral.wrap and peripheral.wrap("front")
  if not (p and p.list) then ledger[d] = nil; return nil end
  local ok, l = pcall(p.list)
  if not ok or type(l) ~= "table" then return nil end
  local items = {}
  for _, st in pairs(l) do items[st.name] = (items[st.name] or 0) + st.count end
  ledger[d] = items
  return items
end
local function inChest(items, tag)
  local n = 0
  for nm, c in pairs(items) do if TAG[tag](nm) then n = n + c end end
  return n
end
local lastReport = -99
local function reportChests(force)                              -- the Foreman shows up on the Storage tab as a read-only warehouse of two chests
  if not fleet.on or not http then return end
  local now = os.clock()
  if not force and now - lastReport < 6 then return end
  lastReport = now
  local total, stacks = {}, 0
  for _, d in ipairs({ 3, 4 }) do
    for nm, c in pairs(ledger[d] or {}) do
      total[nm] = (total[nm] or 0) + c
      stacks = stacks + math.ceil(c / 64)
    end
  end
  local parts = {}
  for nm, c in pairs(total) do parts[#parts + 1] = jq(nm) .. ":" .. c end
  table.sort(parts)
  local body = '{"v":1,"id":' .. os.getComputerID() .. ',"name":' .. jq((PLAN.name or "Foreman") .. "'s chests") ..
    ',"chests":2,"max":2,"stacks":' .. stacks .. ',"slots":54,"spare":0,"items":{' .. table.concat(parts, ",") .. "}}"
  pcall(function()
    local res = http.post({ url = LIVE_URL .. "/storage", body = body, timeout = 5, headers = { ["Content-Type"] = "application/json" } })
    if res then res.readAll(); res.close() end
  end)
end

-- how many of tag I own: in my inventory plus both chests (a fresh look)
local function stock(tag)
  local n = count(tag)
  for _, d in ipairs({ 3, 4 }) do
    local it = listChest(d)
    if it then n = n + inChest(it, tag) end
  end
  turnTo(1)
  reportChests(false)
  return n
end

-- empty myself into the chests (sorting chest first). keep = a set of slots to leave alone
local function stash(keep)
  for s = 1, 16 do
    if itemName(s) and not (keep and keep[s]) then
      turtle.select(s)
      for _, d in ipairs({ 4, 3 }) do
        turnTo(d); turtle.drop()
        if turtle.getItemCount(s) == 0 then break end
      end
    end
  end
  turtle.select(1)
  turnTo(1)
  for s = 1, 16 do if itemName(s) and not (keep and keep[s]) then return false end end
  return true
end

-- take stacks from chest d until I hold n of tag; stacks of other things go to the other chest
local function pullFrom(d, tag, n)
  local other = d == 3 and 4 or 3
  turnTo(d)
  for _ = 1, 60 do
    local want = n - count(tag)
    if want <= 0 or freeSlots() < 2 then break end
    -- v7.6: turtle.suck(n) always takes the chest's FIRST stack, so asking for 1 item of something that is not first just moves the
    -- wrong stack around. We look at p.list() first and only limit the amount when the first stack is what we want.
    local first                                                -- suck always takes the chest's first stack: only ask for a few when that is what I want
    local p = peripheral and peripheral.wrap and peripheral.wrap("front")
    local okL, l = pcall(function() return p.list() end)
    if okL and type(l) == "table" then
      local lo
      for k in pairs(l) do if not lo or k < lo then lo = k end end
      first = lo and l[lo].name
    end
    local wanted = first and TAG[tag](first)
    local before = snapshot()
    if not (wanted and turtle.suck(want) or not wanted and turtle.suck()) then break end
    local after = snapshot()
    for s = 1, 16 do
      local a, b = after[s], before[s]
      if a and (not b or a.count > b.count) and not TAG[tag](a.name) then
        turtle.select(s); turnTo(other); turtle.drop(a.count - (b and b.count or 0)); turnTo(d)
      end
    end
    turtle.select(1)
  end
  turnTo(1)
end
local function take(tag, n)                                      -- bring n of tag into my inventory (it may already be there)
  if count(tag) >= n then return true end
  local have = {}
  for _, d in ipairs({ 3, 4 }) do
    local it = listChest(d)
    have[d] = it and inChest(it, tag) or 0
  end
  local order = have[4] > have[3] and { 4, 3 } or { 3, 4 }
  for _, d in ipairs(order) do
    if have[d] > 0 and count(tag) < n then pullFrom(d, tag, n) end
  end
  return count(tag) >= n
end

local function parseRows(rows)
  local cells = {}
  for r = 1, 3 do
    local i = 0
    for tok in rows[r]:gmatch("%S+") do i = i + 1; cells[(r - 1) * 3 + i] = tok ~= "-" and tok or false end
  end
  return cells
end

-- crafty turtles offer turtle.craft; some versions only give the crafting table's own "workbench" peripheral
local function craftFn()
  if turtle.craft then return turtle.craft end
  for _, side in ipairs({ "left", "right" }) do
    if peripheral and peripheral.getType and peripheral.getType(side) == "workbench" then
      local w = peripheral.wrap(side)
      if w and w.craft then return function(n) return w.craft(n) end end
    end
  end
  return nil
end

local function isMachine(n) return n and (n:find("turtle", 1, true) or n:find("computer", 1, true) or n:find("disk_drive", 1, true)) end

local function clearFront()
  turnTo(1)
  while turtle.detect() do
    local _, data = turtle.inspect()
    local n = type(data) == "table" and data.name or ""
    if isProtected(data) or isMachine(n) then
      say(TITLE, "", "Something is in the way in front:", n, "Waiting...")
      sleep(5)
    else
      turtle.dig()
    end
  end
end

local driveReady = false
-- the disk drive above the spot in front of me, with a floppy whose startup file installs the first-start programs
local function startupText()
  return table.concat({
    "-- written by the Carve foreman: first start of a new turtle",
    "local k = fs.open('carve.kit', 'w'); k.write('1'); k.close()      -- the agent looks for its starter kit chest once",
    "local function get(url, file)",
    "  local r = http and http.get(url)",
    "  if not r then return false end",
    "  local body = r.readAll(); r.close()",
    "  local f = fs.open(file, 'w'); f.write(body); f.close()",
    "  return true",
    "end",
    "get(" .. string.format("%q", PLAN.launcher_url or "") .. ", 'carve.lua')",
    "if get(" .. string.format("%q", PLAN.agent_url or "") .. ", 'agent.lua') then",
    "  local s = fs.open('startup.lua', 'w'); s.write('shell.run(\"agent\")'); s.close()",
    "  shell.run('agent')",
    "else print('Could not download the agent program.') end" }, "\n")
end

-- a disk drive with a floppy from an earlier run stays above the cell in front of me: use it again (nobody has to load it a second time)
local function reuseDrive()
  step(5)
  local okI, blk = turtle.inspect()
  local dv = okI and blk and tostring(blk.name):find("disk_drive", 1, true) and peripheral and peripheral.wrap and peripheral.wrap("front")
  if dv and dv.isDiskPresent and dv.isDiskPresent() and dv.getMountPath and dv.getMountPath() then
    local f = fs.open(dv.getMountPath() .. "/startup.lua", "w")
    f.write(startupText()); f.close()                           -- refresh the first-start program (the addresses may have changed)
    step(6)
    return true
  end
  step(6)
  return false
end

local function bootNew()
  turnTo(1)
  local t = peripheral and peripheral.wrap("front")
  if not (t and t.turnOn) then return nil end
  t.turnOn()
  local id
  for _ = 1, 20 do
    id = t.getID and t.getID()
    if id and id > 0 then return id end
    sleep(1)
  end
  return nil
end

local function doneList()
  local text = readFile("carve.foreman.done") or ""
  local set = {}
  for line in text:gmatch("[^\n]+") do set[line] = true end
  return set
end
local function markDone(name)
  local text = readFile("carve.foreman.done") or ""
  writeFile("carve.foreman.done", text .. name .. "\n")
end

local function waitFor(what, fn, seconds)
  local waited = 0
  while waited < seconds do
    if fn() then return true end
    say(TITLE, "", "Waiting " .. what, math.floor(waited) .. " s of " .. seconds .. " s")
    sleep(3)
    waited = waited + 3
  end
  return false
end

-- lay a recipe out and craft it once. The ingredients come out of the chests in exactly the right numbers, so nothing is left
-- over; the result goes back into a chest. Returns true, or false and why.
-- v7.6: replaces the old craftRows/ensureHave pair. The ingredients are pulled out in exactly the right numbers, so nothing is left over
-- and the inventory outside the grid really is empty when turtle.craft is called.
local function craftGrid(rows)
  local cells, total = parseRows(rows), {}
  for i = 1, 9 do if cells[i] then total[cells[i]] = (total[cells[i]] or 0) + 1 end end
  if not stash() then return false, "both chests are full: empty the chest on my left" end
  for t, c in pairs(total) do
    take(t, c)
    if count(t) < c then stash(); return false, "no " .. t end
  end
  local isStore, isGrid = {}, {}
  for _, s in ipairs(STORE) do isStore[s] = true end
  for _, g in ipairs(GRID) do isGrid[g] = true end
  for s = 1, 16 do                                             -- every stack into the store slots first: the grid is only for the layout
    local nm = itemName(s)
    if nm and not isStore[s] then
      local dest
      for _, d in ipairs(STORE) do
        if itemName(d) == nm and turtle.getItemCount(d) < 64 then dest = d; break end
      end
      for _, d in ipairs(STORE) do
        if not dest and turtle.getItemCount(d) == 0 then dest = d end
      end
      if not dest then stash(); return false, "inventory full" end
      turtle.select(s); turtle.transferTo(dest)
    end
  end
  for i = 1, 9 do
    local t = cells[i]
    if t then
      local donor
      for _, s in ipairs(STORE) do
        local nm = itemName(s)
        if not donor and nm and TAG[t](nm) then donor = s end
      end
      if not donor then stash(); return false, "no " .. t end
      turtle.select(donor); turtle.transferTo(GRID[i], 1)
    end
  end
  stash(isGrid)                                                -- the grid must hold everything I carry
  local cf = craftFn()
  if not cf then stash(); return false, "no crafting table attached" end
  turtle.select(RESULT)
  local ok, err = cf(1)
  if not ok then ok, err = cf() end
  turtle.select(1)
  local seen = {}
  if not ok then
    for i = 1, 9 do seen[i] = (itemName(GRID[i]) or "-"):gsub("^%a+:", "") .. "x" .. turtle.getItemCount(GRID[i]) end
  end
  stash()
  if ok then return true end
  return false, tostring(err or "no recipe") .. " [" .. table.concat(seen, " ") .. "]"
end

local need
local function craftOnce(tag)
  local total = {}
  for _, row in ipairs(R[tag].rows) do
    for t in row:gmatch("%S+") do if t ~= "-" then total[t] = (total[t] or 0) + 1 end end
  end
  crafting[#crafting + 1] = tag
  if fleetSend then fleetSend(false) end                       -- the Foreman tab shows what is being crafted
  for _ = 1, 2 do
    for t, c in pairs(total) do need(t, c) end                 -- every ingredient waits in a chest; a second round catches one that another craft used up
  end
  local ok, why = craftGrid(R[tag].rows)
  crafting[#crafting] = nil
  if ok then recent[#recent + 1] = tag end
  return ok, why
end

-- make sure I own n of tag (in the chests): craft what is missing, or wait for the person to put more in the chest
need = function(tag, n)
  local have = stock(tag)
  local tries, allowed = 0, n - have + 2                       -- more crafts than the shortage needs: this pack does not give me the item, so stop wasting materials
  while have < n do
    local why
    if R[tag] and tries < allowed then
      tries = tries + 1
      local ok
      ok, why = craftOnce(tag)
      if ok then why = nil end
    end
    have = stock(tag)
    if have < n and (why or not R[tag] or tries >= allowed) then
      local word = WORDS[tag] or tag
      local where = "back " .. inChest(ledger[3] or {}, tag) .. " left " .. inChest(ledger[4] or {}, tag)
      if why then
        say(TITLE, "", "Can't craft " .. word .. " here:", tostring(why):sub(1, 40), "Put " .. (n - have) .. " more " .. word .. " in the chest behind me.", where)
      elseif R[tag] then
        say(TITLE, "", "Crafting " .. word .. " does not give me " .. word .. " in this pack.", "Put " .. (n - have) .. " " .. word .. " in the chest behind me.", where)
      else
        say(TITLE, "", "Out of " .. word .. ": need " .. (n - have) .. " more.", "Put them in the chest behind me.", "Waiting... " .. where)
      end
      sleep(10)
    end
  end
end

-- a turtle with a pickaxe (or a crafting table): the upgrade recipes take the tool and the turtle side by side
local function upgrade(tool)
  need(tool, 1); need("turtle", 1)
  local last
  for _, rows in ipairs({ { tool .. " turtle -", "- - -", "- - -" }, { "turtle " .. tool .. " -", "- - -", "- - -" } }) do
    local ok, why = craftGrid(rows)
    if ok then return end
    last = why
  end
  error("could not fit the " .. tool .. " on the turtle: " .. tostring(last), 0)
end
local function makeTurtle(crafty)
  need("turtle", 1)
  upgrade("pickaxe")
  if crafty then upgrade("ctable") end
end

-- eat some of the chest's coal so I can walk (stepping up to the disk drive and back, placing chests); the rest goes back
-- v7.x: the Foreman eats coal from the chest at the start so it can walk (stepping up to the drive, placing chests); it tops up again before each turtle.
local function topUpFuel(target)
  local lvl = turtle.getFuelLevel()
  if lvl == "unlimited" then return end
  target = math.min(target or 1000, turtle.getFuelLimit())
  if lvl >= target then return end
  act("refuelling")
  say(TITLE, "", "Getting some fuel from the chest...", "fuel " .. tostring(lvl) .. " of " .. target)
  take("coal", math.max(1, math.ceil((target - lvl) / 80)))
  burn(target)
  stash()
end

-- the disk drive with its floppy: crafted once, stays above the cell in front of me for every turtle
-- v7.4: the floppy is loaded through a hopper placed on top of the disk drive (needs 5 iron + a chest). v7.3 corrected the drive recipe to the
-- real 7 stone + 2 redstone (a ring of 8 stone around redstone is a WIRED MODEM and wasted stone).
local function ensureDrive()
  if driveReady then return end
  if reuseDrive() then driveReady = true; return end
  for _ = 1, 3 do                                              -- craft all three into the chests first (a craft empties me), then take them
    need("drive", 1); need("disk", 1); need("hopper", 1)
    if stock("drive") >= 1 and stock("disk") >= 1 and stock("hopper") >= 1 then break end
  end
  stash()
  take("drive", 1); take("disk", 1); take("hopper", 1)
  step(5)
  clearFront()
  turtle.select(slotOfTag("drive") or 1)
  local placedDrive, whyDrive = turtle.place()
  turtle.select(1)
  if not placedDrive then error("could not place the disk drive: " .. tostring(whyDrive), 0) end
  local function present(side)
    local dv = peripheral and peripheral.wrap and peripheral.wrap(side or "front")
    return dv and dv.isDiskPresent and dv.isDiskPresent() and dv or nil
  end
  local function waitPresent(secs)
    for _ = 1, secs do
      if present() then return true end
      sleep(1)
    end
    return false
  end
  local function haveDisk()                                    -- a floppy in my inventory (craft another if one fell on the ground)
    if not slotOfTag("disk") then
      for sl = 1, 16 do                                        -- it may be lying in front of me: pick it up
        if turtle.getItemCount(sl) == 0 then turtle.select(sl); turtle.suck(); break end
      end
      turtle.select(1)
    end
    if not slotOfTag("disk") then                              -- the chests are down at the working level: go back, craft one, come up again
      local hadHopper = slotOfTag("hopper") ~= nil
      step(6)
      stash()
      need("disk", 1)
      take("disk", 1)
      if hadHopper then take("hopper", 1) end
      turnTo(1)
      step(5)
    end
    return slotOfTag("disk")
  end
  local inserted = false
  local notes = {}                                              -- what each try said, shown if I have to ask for help
  local hs = slotOfTag("hopper")
  local tries = 3
  if hs then                                                    -- a hopper above the drive feeds it: drop the floppy into the hopper from above
    local sl = haveDisk()
    if sl then
      hs = slotOfTag("hopper") or hs
      step(5); step(5); step(1)                                 -- two cells up and one forward: above the cell over the drive
      turtle.select(hs)
      local okH, whyH = turtle.placeDown()
      notes[#notes + 1] = "hopper " .. tostring(okH) .. (whyH and (" " .. tostring(whyH):sub(1, 18)) or "")
      sl = slotOfTag("disk") or sl
      turtle.select(sl)
      local okD, whyD = turtle.dropDown(1)
      notes[#notes + 1] = "into hopper " .. tostring(okD) .. (whyD and (" " .. tostring(whyD):sub(1, 18)) or "")
      turtle.select(1)
      sleep(2)
      step(3); step(6); step(6); turnTo(1)
      if waitPresent(8) then inserted = true end
      tries = 0                                                 -- dropping it elsewhere would only lose the floppy
    end
  end
  for attempt = 1, tries do
    local sl = haveDisk()
    if not sl then break end
    local okTry, whyTry
    if attempt == 3 then                                       -- from above, the way a hopper would feed it
      step(5); step(1)
      turtle.select(sl)
      okTry, whyTry = turtle.dropDown(1)
      turtle.select(1)
      local seen = false
      for _ = 1, 4 do
        if present("bottom") then seen = true; break end
        sleep(1)
      end
      step(3); step(6); turnTo(1)       -- back to the cell above me, facing the drive
      notes[#notes + 1] = "dropDown " .. tostring(okTry) .. (whyTry and (" " .. tostring(whyTry):sub(1, 18)) or "")
      if seen or waitPresent(2) then inserted = true; break end
    else
      turtle.select(sl)
      if attempt == 1 then okTry, whyTry = turtle.drop(1) else okTry, whyTry = turtle.place() end   -- 1: hand it over; 2: right-click the drive with it
      notes[#notes + 1] = (attempt == 1 and "drop " or "place ") .. tostring(okTry) .. (whyTry and (" " .. tostring(whyTry):sub(1, 18)) or "")
      turtle.select(1)
      if waitPresent(4) then inserted = true; break end
    end
  end
  if not inserted then
    local okI, blk = turtle.inspect()
    notes[#notes + 1] = "front " .. (okI and blk and tostring(blk.name):gsub("^%a+:", "") or "nothing")
    notes[#notes + 1] = "type " .. tostring(peripheral and peripheral.getType and peripheral.getType("front"))
    for waited = 0, 300, 3 do                                   -- neither worked: ask the person standing there
      if present() then inserted = true; break end
      local sl = slotOfTag("disk")
      say(TITLE, "", "Put the floppy in the disk drive in front of me.", sl and ("Take it from my slot " .. sl .. " and right-click the drive.") or "Pick it up from the ground and right-click the drive.", "Waiting... " .. waited .. " s", table.concat(notes, "; "))
      sleep(3)
    end
  end
  local d = present()
  local mount = d and d.getMountPath and d.getMountPath()
  if not mount then error("the disk drive did not take the floppy", 0) end
  local f = fs.open(mount .. "/startup.lua", "w")
  f.write(startupText()); f.close()
  step(6)
  driveReady = true
end

-- A new turtle does not take items from my hands (a turtle is no chest to drop into), so its starter kit goes into a CHEST standing
-- in front of the cell it will be placed in; the new turtle empties that chest by itself when it starts, then I take the chest back.
-- v7.x (before 7.3): the starter kit goes into a chest in front of the new turtle because dropping items into a turtle does nothing here.
-- The new turtle empties the chest (collectKit in auto_agent.lua) and the Foreman takes the chest back afterwards.
local function giveKit(job)
  local want, hasChest = { { "coal", 16 } }, false
  for _, k in ipairs(job.kit or {}) do
    if TAG[k[1]] and k[2] > 0 then
      want[#want + 1] = { k[1], k[2] + (k[1] == "chest" and 1 or 0) }          -- one more chest: the one that carries the kit
      if k[1] == "chest" then hasChest = true end
    end
  end
  if not hasChest then want[#want + 1] = { "chest", 1 } end
  for _ = 1, 2 do
    for _, k in ipairs(want) do need(k[1], k[2]) end           -- all of it waits in the chests; a second round catches one a craft used up
  end
  stash()
  for _, k in ipairs(want) do
    if not take(k[1], k[2]) then error("the kit for " .. job.name .. " is short of " .. (WORDS[k[1]] or k[1]), 0) end
  end
  step(1)                                                       -- onto the cell the new turtle will stand on; the chest goes one further
  turnTo(1)
  local okI, blk = turtle.inspect()
  local there = okI and type(blk) == "table" and tostring(blk.name):find("chest", 1, true)
  if not there then
    clearFront()
    local cs = slotOfTag("chest")
    if not cs then error("no chest to carry the kit", 0) end
    turtle.select(cs)
    local placed, why = turtle.place()
    turtle.select(1)
    if not placed then error("could not place the kit chest: " .. tostring(why), 0) end
  end
  for _, k in ipairs(want) do
    local tag = k[1]
    local left = k[2] - ((tag == "chest" and not there) and 1 or 0)        -- the placed chest is not part of the kit
    for sl = 1, 16 do
      local nm = itemName(sl)
      if left > 0 and nm and TAG[tag](nm) then
        turtle.select(sl)
        local c = math.min(left, turtle.getItemCount(sl))
        if turtle.drop(c) then left = left - c end
      end
    end
    turtle.select(1)
  end
  step(3)
  turnTo(1)
  stash()                                                       -- whatever is left over goes back to the chests
end

-- take the empty kit chest back (the new turtle has left): it is used again for the next one
local function takeKitChest()
  step(1)
  turnTo(1)
  local okI, blk = turtle.inspect()
  if okI and type(blk) == "table" and tostring(blk.name):find("chest", 1, true) then turtle.dig() end
  step(3)
  turnTo(1)
  stash()
end

local function buildAll(problems)
  ensureChest(3, "materials")
  ensureChest(4, "sorting")
  listChest(3); listChest(4); turnTo(1)
  reportChests(true)                                           -- what is in the chests, for the Storage tab
  topUpFuel(1000)
  local done = doneList()
  local todo = {}
  for _, j in ipairs(PLAN.jobs) do
    if j.kind ~= "agent" and j.kind ~= "foreman" then todo[#todo + 1] = j end
  end
  local made = 0
  jobQ = {}
  for _, j in ipairs(todo) do jobQ[#jobQ + 1] = { name = j.name, s = done[j.name] and "done" or "todo" } end
  for i, j in ipairs(todo) do
    fleet.n, fleet.total = i - 1, #todo
    if jobQ[i] and jobQ[i].s ~= "done" then jobQ[i].s = "now" end
    if not done[j.name] then
      say(TITLE, "", "Building the turtle for " .. j.name, i .. " of " .. #todo)
      topUpFuel(400)
      makeTurtle(j.crafty)
      ensureDrive()
      giveKit(j)                                                -- the kit waits in a chest in front of the cell the new turtle will take
      stash()
      take("turtle", 1)
      clearFront()
      turtle.select(slotOfTag("turtle") or 1)
      if not turtle.place() then
        turtle.select(1)
        problems[#problems + 1] = "couldn't place the turtle for " .. j.name
        return made
      end
      turtle.select(1)
      local id = bootNew()
      if not id then
        problems[#problems + 1] = "the new turtle for " .. j.name .. " did not start"
        return made
      end
      ask("spawn", { j }, ',"turtle":' .. id .. ',"rel":[0,0,1]')
      say(TITLE, "", "Waiting for " .. j.name .. "'s turtle", "(#" .. id .. ") to report in...")
      local ready = waitFor("for turtle #" .. id .. " to report", function()
        local lines = ask("ready", { j }, ',"turtle":' .. id)
        return lines and lines[1] == "ready"
      end, 600)
      if not ready then
        problems[#problems + 1] = "turtle #" .. id .. " never reported in (is the app address reachable from it?)"
        return made
      end
      local lines = ask("dispatch", { j }) or {}
      local sent = false
      for _, l in ipairs(lines) do
        if l:match("^sent ") then sent = true elseif l:match("^fail ") then problems[#problems + 1] = l end
      end
      if not sent then return made end
      waitFor("for " .. j.name .. "'s turtle to leave", function() return not turtle.detect() end, 1200)
      takeKitChest()
      markDone(j.name)
      if jobQ[i] then jobQ[i].s = "done" end
      made = made + 1
    end
  end
  fleet.n, fleet.total = #todo, #todo
  return made
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
    say(TITLE, "", "Live reporting is off, so I can't", "ask where the jobs are.", "Upload me with live reporting", "ticked, and start the Fleet tab.")
    return
  end
  installStartup()
  local problems = {}
  if PLAN.build then
    if not craftFn() then                                   -- a plain turtle can become crafty by equipping a crafting table
      local notes, tableSide = {}, nil
      for s = 1, 16 do
        if itemName(s) == "minecraft:crafting_table" then
          turtle.select(s)
          for _, side in ipairs({ "Right", "Left" }) do
            if not craftFn() then
              local ok, res, err = pcall(turtle["equip" .. side])
              notes[#notes + 1] = side .. ": " .. tostring(ok and (res and "ok" or err) or res)
              if ok and res then tableSide = side end
              sleep(0.5)
            end
          end
          turtle.select(1)
          if craftFn() then break end
        end
      end
      if tableSide then                                       -- the tool goes on the other side (equipping on an occupied side swaps)
        for s = 1, 16 do
          if itemName(s) == "minecraft:diamond_pickaxe" then
            turtle.select(s)
            pcall(turtle["equip" .. (tableSide == "Right" and "Left" or "Right")])
            turtle.select(1)
            break
          end
        end
      end
      if not craftFn() then
        removeStartup()
        local eq = {}
        for _, side in ipairs({ "Left", "Right" }) do
          local fn = turtle["getEquipped" .. side]
          if fn then
            local ok, d = pcall(fn)
            eq[#eq + 1] = side:sub(1, 1) .. "=" .. tostring(ok and type(d) == "table" and d.name or ok and d or "?"):gsub("^%a+:", "")
          end
        end
        local sides = {}
        for _, side in ipairs({ "left", "right" }) do
          sides[#sides + 1] = side:sub(1, 1) .. "=" .. tostring(peripheral and peripheral.getType and peripheral.getType(side))
        end
        say(TITLE, "", "I can't craft yet.", "No crafting table is attached.", table.concat(notes, " "):sub(1, 38), "equipped " .. table.concat(eq, " "), "peripherals " .. table.concat(sides, " "))
        finish(TITLE, "", "Can't craft: " .. table.concat(notes, " "):sub(1, 24), "equipped " .. table.concat(eq, " "), "peripherals " .. table.concat(sides, " "))
        return
      end
    end
    if args[1] ~= "resume" then fs.delete("carve.foreman.done") end
    local made = buildAll(problems)
    local msg = made .. " turtles built and sent out."
    if #problems == 0 then
      removeStartup(); fs.delete(STATE_FILE)
      finish(TITLE, "", "Done. " .. msg)
    else
      finish(TITLE, "", msg, problems[1]:sub(1, 38))
    end
    return
  end
  -- 1. where everything goes
  local plan
  while true do
    local lines, why = ask("plan")
    if lines then
      plan = {}
      for _, l in ipairs(lines) do
        local what, name, x, y, z = l:match("^(%a+) (.-) (-?%d+) (-?%d+) (-?%d+)$")
        if what == "chest" or what == "furnace" then
          plan[#plan + 1] = { what = what, name = name, x = tonumber(x), y = tonumber(y), z = tonumber(z) }
        elseif l:match("^skip ") or l:match("^error ") then
          problems[#problems + 1] = l
        end
      end
      local err = problems[1] and problems[1]:match("^error (.*)$")
      if not err then break end
      say(TITLE, "", err, "Waiting...")
      problems = {}
    else
      say(TITLE, "", why or "No answer from the app", "Waiting...")
    end
    sleep(5)
  end
  -- 2. build the chests and furnaces
  for i, p in ipairs(plan) do
    fleet.n, fleet.total = i - 1, #plan
    say(TITLE, "", "Placing " .. p.what .. " for " .. p.name, i .. " of " .. #plan)
    if not travelTo(p.x, p.y, p.z) then
      goTo(p.x, p.y, p.z, "xzy")                            -- the gentle way failed: dig a path, level first (never down onto a chest)
    end
    if not placeHere(p.what, p.name) then
      problems[#problems + 1] = "couldn't place the " .. p.what .. " for " .. p.name
    end
  end
  fleet.n, fleet.total = #plan, #plan
  if not travelTo(0, 0, 0) then goTo(0, 0, 0, "xzy") end
  turnTo(1)
  -- 3. hand every job to an idle agent
  local sent = 0
  if PLAN.dispatch then
    say(TITLE, "", "Chests and furnaces are in place.", "Sending the jobs to idle agents...")
    local lines = ask("dispatch") or {}
    for _, l in ipairs(lines) do
      if l:match("^sent ") then sent = sent + 1 elseif l:match("^fail ") then problems[#problems + 1] = l end
    end
  end
  removeStartup()
  fs.delete(STATE_FILE)
  local msg = placed.chest .. " chests, " .. placed.furnace .. " furnaces placed."
  if PLAN.dispatch then msg = msg .. " " .. sent .. " jobs sent." end
  if #problems > 0 then
    finish(TITLE, "", msg, problems[1]:sub(1, 38), (#problems > 1) and ("(+" .. (#problems - 1) .. " more, see the app)") or "")
  else
    finish(TITLE, "", "Done. " .. msg)
  end
end

if rawget(_G, "CARVE_TEST") then
  return { main = main, pos = pos }
end
runMain(main)
'''
# ============================================================ three.js (MIT licence) for the 3D page
# three.js r149 (https://threejs.org), gzip + base64. It is written into the 3D pages you export so they work offline.
THREE_JS_GZ = (
    "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"
    "LlBQZ1Sx1lWqkenYy9L+f9PdjzFbuqpkU5tHsgTrCUSTpgShy4hH2HBm08Ny5llTjvEbl4PyVQt1bTpTx57rWJq+C71Dra3Ju9D71Po2U9Rbe75EWQ63PHPY"
    "q7GWWapRcsWNnhqneWZLK+/J8/Tlk4ZbMtuUUn6bq6FpZByCccN6Qk19yefVIpOWkBOBshD7SEuxj1iMfaTl2EcsyD7SkuwjFmUfaVn20Q3C7CNbmn3kirOP"
    "XHn2kSPQ3jxkt5B0H7mi7iNX1n3kCruPbi3tPiqJu49K8u6jksD7qCTx1k0rEQZ+m5WidUVnfLpRnn3kCLSPHIn2kSPSPtIy7XQjs7r+Ka2yAepfbwNkWFC6"
    "pUaCSbZ0E0fraLO1ztcY6fwLbXP+heY3/3MNbf69NjVfZ0zzlSYzX2km882MY76hNcxX2r98pc3LN7N0+TOmLX/GnEWXvb4VDbcVDbcVDTOOZBIjmc4uGE6x"
    "jEGmkcusgzdqUdrjrt0OhluofuXaAt/ONGeTRU4mLHLoSWjQmPQQtOLU4XV5YYmTCWsdevFZpYEQExY4mbDSydiSx+ql616/9dB3uRNfYXVkP7fd3allwuwn"
    "E2Y/mTT7ycjsp+41vqZbPzCtoKzwUt7ItemB7gfZ1n2Zq29yEctN9chI1tuR2QY625U/xrdt4TnfCy/ogWfEpCwigU0OWTc1Elw0YjLNQa14Khl3t4QsdKhu"
    "PLuAV5FBlyMyQhCcuEbi9cESV8R1o5VBAkccx0ZLt3sqUnLIIlvgCiJZtXUhUkKw2OHgFwWlORVICNIJuWbAB9qPBjzjLmdP2GNZVPezSECa51u/ggj+VsD9"
    "kptqsJCwrPEf4Qm2afElI3PTshp4y8NeVtZ0Ki0rexKVmXhC37e0F+5Yu+mOtZvumN30Sy3e/j3WM/8mC5n/kVYw/8NsW/73Wa38a21T/vUmKP/XGpr8eZuR"
    "LzQS+TOWId/CFuSbWn/8rzH2+HdYdVxN8Upf7reYI3XNkpnvRrrseMGNF8x4YkHTAUCs+AvmxF96h7zglIf6XG/kYKCnmrfBvPTcoYxeJOoKaMuwzaw9qOKl"
    "G0mXxTkXgjkSM+y4PGTF0fRGOK4bHF7iQWSbeIDOgVFDbpdRlfqxuHouI2JHnCwr6DCRvKn6XsOSJtYdKWTZOt6a09QpDbuHyl0kWap4qcI5qERVpnOMjJNf"
    "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"
)
# The route simulator (what the turtle will do, in order) and the small web server (LiveServer) the turtles talk to.
# Why together: the 3D viewer, the fleet page and the turtles all read the same simulated/live state.
# ============================================================ route simulator & view state
# Directions as the turtle numbers them: 1=+z (forward) 2=+x (right) 3=-z 4=-x 5=up 6=down
DX = (0, 1, 0, -1, 0, 0)
DZ = (1, 0, -1, 0, 0, 0)
DY = (0, 0, 0, 0, 1, -1)


class Sim:
    """Result of replaying the turtle's routine on a design.

    events: ('t', face) a turn | ('d', x, y, z) a block dug | ('m', x, y, z) a move
            | ('p', x, y, z) a block / torch placed
    """

    def __init__(self):
        self.events = []
        self.moves = self.digs = self.turns = self.places = 0
        self.total = 0

    @property
    def seconds(self):
        return (self.moves + self.digs + self.turns + self.places) * ACTION_SECONDS


def simulate(design):
    """Replay the turtle program's exact routine (same dig pattern, same path search, same torches).

    It assumes an ideal world: every block breaks, no mobs, the turtle always has the items it
    places, and it never has to stop to empty its inventory (that depends on what it digs up).
    """
    run, total, _skipped = build_run(design)
    sim = Sim()
    sim.total = total
    start = design.turtle
    w, d, h = design.w, design.d, design.h
    pattern, tmode = design.pattern, design.torch_mode
    targets = build_place(design)                       # cell -> slot
    torch_cells = {c for c, sl in targets.items() if "torch" in design.inv[sl]}
    mined = {start}
    placed = set()
    heap = []                                   # (rank, cell): unmined cells next to dug-out ones
    in_heap = set()
    dropped = set()
    pos = start
    face = 1
    ev = sim.events

    def inside(c):
        return 1 <= c[0] <= w and 1 <= c[1] <= h and 1 <= c[2] <= d

    def idx(c):
        return ((c[1] - 1) * d + (c[2] - 1)) * w + c[0]

    def nb(c, k):                                       # neighbour of c in direction k (1..6)
        return (c[0] + DX[k - 1], c[1] + DY[k - 1], c[2] + DZ[k - 1])

    def turn_to(f):
        nonlocal face
        diff = (f - face) % 4
        if diff == 0:
            return
        for s in {1: (1,), 2: (1, 1), 3: (-1,)}[diff]:       # right, right+right, or one left
            face = (face - 1 + s) % 4 + 1
            ev.append(("t", face))
            sim.turns += 1

    def has_work(c):
        for k in range(1, 7):
            n = nb(c, k)
            if n in run and n not in mined:
                return True
        return False

    def bfs(goal):
        order = (face, face % 4 + 1, (face + 1) % 4 + 1, (face + 2) % 4 + 1, 5, 6)
        par = {pos: None}
        pdir = {}
        queue_ = collections.deque([pos])
        while queue_:
            c = queue_.popleft()
            if goal(c):
                path = []
                while par[c] is not None:
                    path.append(pdir[c])
                    c = par[c]
                path.reverse()
                return path
            for k in order:
                n = nb(c, k)
                if n not in par and n in mined and n not in placed and inside(n):
                    par[n] = c
                    pdir[n] = k
                    queue_.append(n)
        return None

    def step(k):
        nonlocal pos
        if k <= 4:
            turn_to(k)
        pos = nb(pos, k)
        ev.append(("m",) + pos)
        sim.moves += 1

    # ---- dig pattern: where a cell comes in the order (mirrors rankOf in the turtle program)
    def outward(v, v0, mx):
        return v - v0 if v >= v0 else mx - v

    def rank(c):
        x, y, z = c
        if pattern == "lanes":
            rel = y - design.ty
            b = (rel + 1) // 3
            up = (h - design.ty + 1) // 3
            br = b if b >= 0 else up - b
            mid = design.ty + 3 * b
            v = 0 if y == mid else (1 if y == mid + 1 else 2)
            xl = w - x
            zr = (z - 1) if xl % 2 == 0 else (d - z)
            return ((br * w + xl) * d + zr) * 3 + v
        lr = outward(y, design.ty, h)
        ri = outward(z, design.tz, d)
        xr = (w - x) if ri % 2 == 0 else (x - 1)
        return (lr * d + ri) * w + xr

    def frontier_add(n):
        for k in range(1, 7):
            m = nb(n, k)
            if m in run and m not in mined and m not in in_heap:
                in_heap.add(m)
                dropped.discard(m)
                heapq.heappush(heap, (rank(m), m))

    def min_frontier():
        while heap:
            n = heap[0][1]
            if n not in mined and n not in dropped and any(
                    nb(n, k) in mined and nb(n, k) not in placed for k in range(1, 7)):
                return n
            heapq.heappop(heap)
            in_heap.discard(n)
        return None

    # ---- torches
    def can_block(n):
        want = len(run - placed - {n})
        seen = {start}
        stack = [start]
        while stack:
            c = stack.pop()
            for k in range(1, 7):
                m = nb(c, k)
                if m not in seen and m != n and m in run and m not in placed:
                    seen.add(m)
                    stack.append(m)
        if len(seen) != want:
            return False
        open_cells = {c for c in mined if c not in placed and c != n}
        seen = {start}
        stack = [start]
        while stack:
            c = stack.pop()
            for k in range(1, 7):
                m = nb(c, k)
                if m not in seen and m in open_cells:
                    seen.add(m)
                    stack.append(m)
        return len(seen) == len(open_cells)

    def place_now(n):
        placed.add(n)
        ev.append(("p",) + n)
        sim.places += 1

    # torches are dropped straight down from the cell above (see putTorch in the turtle program)
    torch_list = sorted(torch_cells, key=idx)
    deferred = set()

    def spot(n):
        return (n[0], n[1] + 1, n[2])

    def support_ready(n):
        b = (n[0], n[1] - 1, n[2])
        if not inside(b) or b not in run:
            return True
        sl = targets.get(b)
        if sl is not None and "torch" not in design.inv[sl]:
            return b in placed
        return False

    def torch_ready(n):
        return n not in placed and n not in deferred and support_ready(n)

    def put_torch(n):
        a = spot(n)
        for k in bfs(lambda c, g=a: c == g) or []:
            step(k)
        if n in run and n not in mined:
            dig_cell(n, 6)
        if n not in mined:
            return
        if not can_block(n):
            deferred.add(n)
            return
        place_now(n)

    def dig_cell(n, k):
        if k <= 4:
            turn_to(k)
        mined.add(n)
        ev.append(("d",) + n)
        sim.digs += 1
        frontier_add(n)
        return True

    def wanted(n):
        return n in run and n not in mined

    def dig_neighbors():
        order = [5, 6] + [(face - 1 + k) % 4 + 1 for k in range(4)]
        for k in order:
            n = nb(pos, k)
            if wanted(n):
                dig_cell(n, k)

    def dig_vertical():
        for k in (5, 6):
            n = nb(pos, k)
            if wanted(n):
                dig_cell(n, k)

    def dig_target(t):
        def goal(c):
            return any(nb(c, k) == t for k in range(1, 7))
        path = bfs(goal)
        if path is None:
            return None
        for k in path:
            step(k)
        for k in range(1, 7):
            if nb(pos, k) == t:
                return dig_cell(t, k)
        return None

    mission = None

    def find_mission():
        spot_of = {}
        for n in torch_list:
            if torch_ready(n):
                a = spot(n)
                if (a in mined or wanted(a)) and a not in placed:
                    spot_of[a] = n
        if not spot_of:
            return None
        par = {}
        queue_ = collections.deque()
        for c in sorted((c for c in mined if c not in placed), key=idx):
            par[c] = None
            queue_.append(c)
            if c in spot_of:
                return {"path": [], "n": spot_of[c]}
        while queue_:
            c = queue_.popleft()
            for k in range(1, 7):
                n = nb(c, k)
                if n not in par and inside(n) and wanted(n):
                    par[n] = c
                    if n in spot_of:
                        rev = []
                        cur = n
                        while par[cur] is not None:
                            rev.append(cur)
                            cur = par[cur]
                        rev.reverse()
                        return {"path": rev, "n": spot_of[n]}
                    queue_.append(n)
        return None

    def mission_step():
        nonlocal mission
        if tmode != "first" or not torch_list:
            return False
        if mission:
            while mission["path"] and not wanted(mission["path"][0]):
                mission["path"].pop(0)
            if not torch_ready(mission["n"]):
                mission = None
        if mission is None:
            mission = find_mission()
        if mission is None:
            return False
        if mission["path"]:
            if dig_target(mission["path"][0]) is None:
                mission = None
                return False
        else:
            n = mission["n"]
            mission = None
            a = spot(n)
            if a in mined and a not in placed:
                put_torch(n)
        return True

    def ready_step():
        if tmode != "early" or not torch_list:
            return False
        spots = {}
        for n in torch_list:
            if n in mined and torch_ready(n):
                a = spot(n)
                if a in mined and a not in placed:
                    spots[a] = n
        if not spots:
            return False
        path = bfs(lambda c: c in spots)
        if path is None:
            return False
        for k in path:
            step(k)
        put_torch(spots[pos])
        return True

    def nearest_step():
        dig_neighbors()
        path = bfs(has_work)
        if not path:
            return False
        for k in path:
            step(k)
        return True

    def ordered_step():
        if pattern == "lanes":
            dig_vertical()
        t = min_frontier()
        if t is None:
            return False
        if dig_target(t) is None:
            dropped.add(t)
        return True

    # ---- dig everything
    frontier_add(start)
    ordered = pattern != "nearest"
    guard = 0
    while True:
        if not mission_step() and not ready_step():
            if ordered:
                if not ordered_step():
                    break
            elif not nearest_step():
                break
        guard += 1
        if guard > 400000:
            break
    if ordered:
        while nearest_step():
            guard += 1
            if guard > 400000:
                break

    # ---- place whatever is still waiting (blocks, and torches that couldn't go in earlier),
    # farthest from the start first so the way home stays open
    if targets:
        dist = {start: 0}
        queue_ = collections.deque([start])
        while queue_:
            c = queue_.popleft()
            for k in range(1, 7):
                n = nb(c, k)
                if n not in dist and n in mined and n not in placed and inside(n):
                    dist[n] = dist[c] + 1
                    queue_.append(n)
        order = sorted((c for c in targets if c in dist and c != start and c not in placed
                        and c not in torch_cells),
                       key=lambda c: (-dist[c], idx(c)))
        for t in order:
            stand = None
            for k in range(1, 7):                                   # same direction order as the turtle
                a = (t[0] - DX[k - 1], t[1] - DY[k - 1], t[2] - DZ[k - 1])
                if inside(a) and dist.get(a) == dist[t] - 1:
                    stand, kdir = a, k
                    break
            if stand is None:
                continue
            for k in bfs(lambda c, g=stand: c == g) or []:
                step(k)
            if kdir <= 4:
                turn_to(kdir)
            place_now(t)
    if torch_list:                                              # torches that had to wait for their floor
        dist = {start: 0}
        queue_ = collections.deque([start])
        while queue_:
            c = queue_.popleft()
            for k in range(1, 7):
                n = nb(c, k)
                if n not in dist and n in mined and n not in placed and inside(n):
                    dist[n] = dist[c] + 1
                    queue_.append(n)
        todo = [n for n in torch_list if n in mined and n not in placed and support_ready(n) and spot(n) in dist]
        todo.sort(key=lambda n: (-dist[spot(n)], idx(n)))
        for n in todo:
            path = bfs(lambda c, g=spot(n): c == g)
            if path is None:
                continue
            for k in path:
                step(k)
            place_now(n)
    home = bfs(lambda c: c == start)
    if home is not None:
        for k in home:
            step(k)
        if design.chest:
            turn_to(3)
        turn_to(1)
    return sim


class ViewState:
    """What the viewer shows: which cells are dug, where the turtle is, where it has been."""

    def __init__(self, design):
        self.design = design
        self.mined = {design.turtle}
        self.pos = design.turtle
        self.face = 1
        self.trail = collections.deque([design.turtle], maxlen=300)
        self.moves = 0
        self.turns = 0
        self.placed = set()

    def apply(self, ev):
        k = ev[0]
        if k == "t":
            self.face = ev[1]
            self.turns += 1
        elif k == "d":
            self.mined.add(ev[1:])
        elif k == "p":
            self.placed.add(ev[1:])
        else:
            self.pos = ev[1:]
            self.trail.append(self.pos)
            self.moves += 1


# =================================================================== live view
class LiveSession:
    """Everything one turtle has reported to us."""

    def __init__(self, turtle_id):
        self.id = turtle_id
        self.design = None
        self.view = None
        self.name = ""
        self.count = 0
        self.total = 0
        self.fuel = ""
        self.msg = ""
        self.done = False
        self.stopped = False
        self.placed_count = self.placed_total = 0
        self.last_seen = 0.0
        self.waiting_for_sync = True
        self.new_design = False          # set when the design object was replaced

    def apply(self, p):
        """Fold one report into the session. Raises ValueError on nonsense."""
        if not isinstance(p, dict) or p.get("v") != 1:
            raise ValueError("not a Carve report")
        w, d, h = int(p["w"]), int(p["d"]), int(p["h"])
        if "layers" in p:                                   # full picture (start, resume, every 30 s)
            des = design_from_flat(p.get("name", ""), w, d, h, (p["tx"], p["ty"], p["tz"]),
                                   p.get("chest", True), p["layers"], str(p.get("place", "")),
                                   p.get("inv") or None)
            full = str(p.get("full", ""))
            if len(full) != w * d * h:
                raise ValueError("bad progress data")
            same = (self.design is not None and self.design.to_json() == des.to_json())
            if not same:
                self.design = des
                self.view = ViewState(des)
                self.new_design = True
            mined = {des.turtle}
            for i, ch in enumerate(full):
                if ch == "1":
                    mined.add(cell_from_index(i + 1, w, d))
            self.view.mined = mined
            placed = str(p.get("placed", ""))
            if placed and len(placed) != w * d * h:
                raise ValueError("bad progress data")
            self.view.placed = {cell_from_index(i + 1, w, d) for i, ch in enumerate(placed) if ch == "1"}
            self.waiting_for_sync = False
        if self.design is None:
            return False                                    # joined mid-run; wait for the next full picture
        for i in p.get("cells", []):
            self.view.mined.add(cell_from_index(int(i), w, d))
        for i in p.get("pl", []):
            self.view.placed.add(cell_from_index(int(i), w, d))
        self.placed_count, self.placed_total = int(p.get("pc", 0)), int(p.get("pt", 0))
        path = p.get("path", [])
        for j in range(0, len(path) - 2, 3):
            c = (int(path[j]), int(path[j + 1]), int(path[j + 2]))
            self.view.pos = c
            self.view.trail.append(c)
            self.view.moves += 1
        self.view.pos = (int(p["x"]), int(p["y"]), int(p["z"]))
        self.view.face = int(p.get("f", 1))
        self.name = str(p.get("name", ""))
        self.count, self.total = int(p.get("mined", 0)), int(p.get("total", 0))
        self.fuel, self.msg = str(p.get("fuel", "")), str(p.get("msg", ""))
        self.done = bool(p.get("done", False))
        self.stopped = bool(p.get("stopped", False))
        self.last_seen = time.time()
        return True


class LiveServer:
    """A tiny local web server the turtle POSTs its progress to."""

    def __init__(self, host, port, on_payload, fleet=None):
        self.host, self.port, self.on_payload, self.fleet = host, port, on_payload, fleet
        self.httpd = None
        self.thread = None

    def start(self):
        on_payload, fleet = self.on_payload, self.fleet

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _reply(self, code, text):
                raw = text.encode("utf-8")
                self.send_response(code)
                self.send_header("Content-Type", "text/plain; charset=utf-8")
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

            def do_GET(self):
                path = self.path.split("?")[0]
                if fleet is not None and path == "/debug":
                    return self._reply(200, fleet.debug_text(60))
                if fleet is not None and path == "/":
                    fleet.note("web page opened from %s" % self.client_address[0])
                if fleet is not None and path in ("/three.min.js", "/turtle3d.js"):
                    raw = (three_source() if path == "/three.min.js" else TURTLE3D_JS).encode("utf-8")
                    self.send_response(200)
                    self.send_header("Content-Type", "application/javascript; charset=utf-8")
                    self.send_header("Cache-Control", "max-age=3600")
                    self.send_header("Content-Length", str(len(raw)))
                    self.end_headers()
                    self.wfile.write(raw)
                    return
                if fleet is not None and path == "/icons":
                    # item pictures for the web page: your imported textures first, our simplified vanilla tiles next, nothing for
                    # modded items without a texture (the page draws those as a solid colour)
                    q = urllib.parse.parse_qs(self.path.partition("?")[2])
                    out = {}
                    for nm in (q.get("names", [""])[0].split(","))[:160]:
                        if not re.fullmatch(r"[a-z0-9_.\-]+:[a-z0-9_./\-]+", nm or "") or len(nm) > 90:
                            continue
                        try:
                            t = pack_tile(nm) or item_tile(nm)
                        except Exception:
                            t = None
                        if t:
                            out[nm] = _pack_encode(t)
                    raw = json.dumps(out).encode("utf-8")
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Cache-Control", "no-store")
                    self.send_header("Content-Length", str(len(raw)))
                    self.end_headers()
                    self.wfile.write(raw)
                    return
                if fleet is not None and path == "/map3d":
                    q = urllib.parse.parse_qs(self.path.partition("?")[2])

                    def qn(k, d, lo, hi):
                        try:
                            return max(lo, min(hi, int(q.get(k, [d])[0])))
                        except ValueError:
                            return d
                    names, cells, cut = fleet.world.view3d(qn("cx", 0, -3 * 10 ** 7, 3 * 10 ** 7), qn("cy", 64, -2048, 2048),
                                                           qn("cz", 0, -3 * 10 ** 7, 3 * 10 ** 7), qn("r", 40, 4, 120), qn("ry", 40, 2, 200))
                    raw = json.dumps({"names": names, "cells": cells, "truncated": cut, "count": fleet.world.count,
                                      "turtles": [r for r in fleet.snapshot() if r["world"]]}).encode("utf-8")
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Cache-Control", "no-store")
                    self.send_header("Content-Length", str(len(raw)))
                    self.end_headers()
                    self.wfile.write(raw)
                    return
                if fleet is not None and path in ("/", "/fleet", "/map", "/storage"):
                    if path == "/":
                        raw = FLEET_HTML.encode("utf-8")
                        ctype = "text/html; charset=utf-8"
                    elif path == "/fleet":
                        raw = json.dumps({"turtles": fleet.snapshot()}).encode("utf-8")
                        ctype = "application/json"
                    elif path == "/storage":
                        raw = json.dumps(fleet.storage_view()).encode("utf-8")
                        ctype = "application/json"
                    else:
                        q = urllib.parse.parse_qs(self.path.partition("?")[2])

                        def qi(k, d, lo, hi):
                            try:
                                return max(lo, min(hi, int(q.get(k, [d])[0])))
                            except ValueError:
                                return d
                        names, cells = fleet.world.view(qi("cx", 0, -3 * 10 ** 7, 3 * 10 ** 7), qi("cz", 0, -3 * 10 ** 7, 3 * 10 ** 7),
                                                        qi("r", 40, 4, 120), "slice" if q.get("mode", [""])[0] == "slice" else "top",
                                                        qi("y", 64, -2048, 2048))
                        raw = json.dumps({"names": names, "cells": cells, "count": fleet.world.count,
                                          "turtles": [r for r in fleet.snapshot() if r["world"]],
                                          "waiting": fleet.map_waiting()}).encode("utf-8")
                        ctype = "application/json"
                    self.send_response(200)
                    self.send_header("Content-Type", ctype)
                    self.send_header("Cache-Control", "no-store")
                    self.send_header("Content-Length", str(len(raw)))
                    self.end_headers()
                    self.wfile.write(raw)
                    return
                self._reply(200, "Carve Designer live view is listening.\n")

            def do_POST(self):
                path = self.path.split("?")[0]
                ip = self.client_address[0]
                try:
                    n = int(self.headers.get("Content-Length", "0"))
                    if n <= 0 or n > 8 * 1024 * 1024:
                        if fleet is not None:
                            fleet.note("rejected %s from %s: bad size" % (path, ip))
                        return self._reply(400, "bad size")
                    data = json.loads(self.rfile.read(n).decode("utf-8"))
                except Exception:
                    if fleet is not None:
                        fleet.note("rejected %s from %s: not JSON" % (path, ip))
                    return self._reply(400, "bad request")
                if fleet is not None and isinstance(data, dict):
                    who = "turtle %s%s" % (data.get("id", "?"), (" '%s'" % data["name"]) if data.get("name") else "")
                    fleet.note("%s from %s: %s" % (path, ip, who) + (" - " + str(data.get("msg"))[:60] if data.get("msg") else ""),
                               turtle=path in ("/status", "/update", "/map", "/storage", "/route", "/setup"), addr=ip)
                if fleet is not None and path in ("/cmd", "/forget"):
                    tid = data.get("id") if isinstance(data, dict) else None
                    if not isinstance(tid, int):
                        return self._reply(400, "bad id")
                    if path == "/forget":
                        fleet.forget(tid)
                        return self._reply(200, "ok")
                    return self._reply(200 if fleet.command(tid, data.get("cmd"), data.get("arg", "")) else 400, "ok")
                if fleet is not None and path == "/storage":
                    try:
                        return self._reply(200, fleet.report_storage(data))
                    except ValueError:
                        return self._reply(400, "bad storage report")
                if fleet is not None and path == "/order":
                    try:
                        tid = fleet.order_item(data.get("item"), data.get("count"), data.get("keeper") if isinstance(data.get("keeper"), int) else None)
                    except (ValueError, AttributeError) as e:
                        return self._reply(400, str(e))
                    return self._reply(200, "ok %d" % tid)
                if path == "/setup" and fleet is not None:
                    try:
                        if not isinstance(data.get("id"), int) or data.get("action") not in ("plan", "dispatch", "spawn", "ready"):
                            raise ValueError("bad setup request")
                        if data["action"] == "spawn":
                            return self._reply(200, fleet.setup_spawn(data["id"], data.get("turtle"), data.get("rel")))
                        if data["action"] == "ready":
                            return self._reply(200, fleet.setup_ready(data.get("turtle")))
                        fn = fleet.setup_plan if data["action"] == "plan" else fleet.setup_dispatch
                        return self._reply(200, fn(data["id"], data.get("jobs")))
                    except ValueError as e:
                        return self._reply(400, str(e))
                if path == "/route" and fleet is not None:
                    legs = data.get("legs") if isinstance(data, dict) else None
                    if not isinstance(data.get("id"), int) or not isinstance(legs, list) or not all(isinstance(l, dict) for l in legs):
                        return self._reply(400, "bad route request")
                    return self._reply(200, fleet.route(data["id"], legs))
                if path == "/map":
                    try:
                        if fleet is None:
                            raise ValueError("fleet off")
                        fleet.report_map(data)
                    except ValueError:
                        return self._reply(400, "bad report")
                    return self._reply(200, "ok")
                if path == "/status":
                    try:
                        if fleet is None:
                            raise ValueError("fleet off")
                        fleet.report_status(data)
                    except ValueError:
                        return self._reply(400, "bad report")
                else:
                    on_payload(data)
                    if fleet is not None:
                        fleet.report_update(data)
                tid = data.get("id") if isinstance(data, dict) else None
                self._reply(200, fleet.reply_for(tid) if fleet is not None and isinstance(tid, int) else "ok")

        self.httpd = ThreadingHTTPServer((self.host, self.port), Handler)
        self.httpd.daemon_threads = True
        self.port = self.httpd.server_address[1]
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()

    def stop(self):
        if self.httpd:
            self.httpd.shutdown()
            self.httpd.server_close()
            self.httpd = None
# Builds the stand-alone 3D page (viewer3d.html + turtle3d.js) that shows the turtle's whole route in a browser.
# ============================================================ the 3D page (opens in any web browser)
VIEWER_TEMPLATE = r'''<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>@@TITLE@@ - Carve 3D preview</title>
<style>
  :root { --bg:#14171a; --panel:#1d2227ee; --line:#323941; --text:#e6edf3; --dim:#8b949e; --accent:#f0a030; }
  * { box-sizing:border-box; }
  html,body { margin:0; height:100%; background:var(--bg); color:var(--text);
              font:14px/1.4 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif; overflow:hidden; }
  #c { position:fixed; inset:0; width:100%; height:100%; display:block; touch-action:none; cursor:grab; }
  #c.drag { cursor:grabbing; }
  #hud { position:fixed; top:12px; left:12px; right:12px; display:flex; gap:12px; align-items:flex-start;
         justify-content:space-between; pointer-events:none; flex-wrap:wrap; }
  .card { background:var(--panel); border:1px solid var(--line); border-radius:10px; padding:10px 14px;
          backdrop-filter:blur(6px); pointer-events:auto; }
  #title { font-size:16px; font-weight:600; }
  #sub { color:var(--dim); font-size:12px; margin-top:2px; }
  #stats { display:grid; grid-template-columns:auto auto; gap:2px 14px; font-variant-numeric:tabular-nums; font-size:13px; }
  #stats span:nth-child(odd) { color:var(--dim); }
  #legend { display:flex; gap:12px; flex-wrap:wrap; font-size:12px; color:var(--dim); margin-top:8px; }
  #legend i { display:inline-block; width:14px; height:10px; border-radius:2px; margin-right:5px; vertical-align:-1px; }
  #bar { position:fixed; left:12px; right:12px; bottom:12px; display:flex; gap:10px; align-items:center; flex-wrap:wrap; }
  #bar .grow { flex:1 1 260px; display:flex; align-items:center; gap:10px; min-width:200px; }
  button { background:#2b3238; color:var(--text); border:1px solid var(--line); border-radius:8px; padding:7px 12px;
           font:inherit; cursor:pointer; }
  button:hover { background:#353d45; }
  button.primary { background:var(--accent); color:#1a1205; border-color:var(--accent); font-weight:600; min-width:84px; }
  input[type=range] { accent-color:var(--accent); width:100%; }
  select { background:#2b3238; color:var(--text); border:1px solid var(--line); border-radius:8px; padding:6px 8px; font:inherit; }
  label.chk { display:flex; gap:6px; align-items:center; color:var(--dim); font-size:13px; white-space:nowrap; }
  #layerbox { display:flex; align-items:center; gap:8px; min-width:190px; color:var(--dim); font-size:13px; }
  #layerbox input { width:110px; }
  #foot { position:fixed; right:14px; bottom:74px; color:#6b737c; font-size:11px; pointer-events:none; text-align:right; }
  #fail { position:fixed; inset:0; display:none; align-items:center; justify-content:center; padding:30px; text-align:center; }
  body.rec #hud, body.rec #bar, body.rec #foot, body.rec #recpanel { display:none !important; }
  body.rec #c { inset:auto; left:50%; top:50%; transform:translate(-50%,-50%); cursor:default;
                width:min(100vw, calc(100vh * 16 / 9)); height:min(100vh, calc(100vw * 9 / 16)); }
  #recbadge { position:fixed; top:12px; left:50%; transform:translateX(-50%); display:none; gap:12px; align-items:center;
              z-index:5; }
  body.rec #recbadge { display:flex; }
  #recbadge b { color:#ff5b5b; }
  #recpanel { position:fixed; inset:0; display:none; align-items:center; justify-content:center; padding:16px; z-index:10;
              background:#0009; }
  #recpanel.open { display:flex; }
  #recpanel .card { width:min(460px, 100%); max-height:100%; overflow:auto; }
  #recpanel h3 { margin:0 0 6px; font-size:16px; }
  #recpanel .row { display:flex; gap:10px; align-items:center; margin:8px 0; color:var(--dim); }
  #recpanel .row select { flex:1; }
  #recpanel .note { color:var(--dim); font-size:12px; margin-top:8px; }
  #recpanel video { width:100%; border-radius:8px; margin-top:8px; background:#000; }
  a.btn { display:inline-block; text-decoration:none; background:#2b3238; color:var(--text); border:1px solid var(--line); border-radius:8px; padding:7px 12px; }
  a.btn:hover { background:#353d45; }
  #recpanel a.btn { display:inline-block; text-decoration:none; background:var(--accent); color:#1a1205; font-weight:600;
                    border-radius:8px; padding:8px 14px; }
  @media (max-width:640px) { #hud { top:8px; left:8px; right:8px; } #bar { left:8px; right:8px; bottom:8px; } #foot { display:none; } }
</style>
</head>
<body>
<canvas id="c"></canvas>
<div id="hud">
  <div class="card">
    <div id="title"></div>
    <div id="sub"></div>
    <div id="legend">
      <span id="lg-dig"><i style="background:linear-gradient(90deg,#f0a030,#4fd37a,#3b8fe8)"></i>to dig (colour = layer)</span>
      <span id="lg-skip"><i style="background:#d9534f"></i>skipped (not connected)</span>
      <span id="lg-place"><i style="background:#9aa0a6"></i>placed blocks &amp; torches</span>
      <span><i id="lg-turtle" style="background:#6fe36f"></i>turtle</span>
      <span id="lg-chest"><i style="background:#a0682d"></i>chest</span>
    </div>
  </div>
  <div class="card"><div id="stats"></div></div>
  <div class="card" id="sharebar" style="display:none">
    <div style="font-weight:600;margin-bottom:6px">Shared design</div>
    <div style="display:flex;gap:8px;flex-wrap:wrap">
      <a class="btn" id="sh-gallery" href="#">All designs</a>
      <button id="sh-copy">Copy turtle command</button>
      <a class="btn" id="sh-file" href="#" download>Download design file</a>
    </div>
    <div id="sh-note" style="color:var(--dim);font-size:12px;margin-top:6px;max-width:300px"></div>
  </div>
</div>
<div id="foot">drag = rotate &middot; right-drag / shift-drag = move &middot; wheel / pinch = zoom &middot; space = play/pause</div>
<div id="bar">
  <div class="card" style="display:flex;gap:8px;align-items:center">
    <button id="reset" title="Back to the start">&#9198;</button>
    <button id="play" class="primary">Play</button>
    <button id="back" title="One step back (left arrow)">&#9664;</button>
    <button id="fwd" title="One step forward (right arrow)">&#9654;</button>
  </div>
  <div class="card grow"><input id="seek" type="range" min="0" max="1" value="0" step="1"><span id="pct" style="min-width:42px;text-align:right;color:var(--dim)">0%</span></div>
  <div class="card" style="display:flex;gap:12px;align-items:center;flex-wrap:wrap">
    <label class="chk">Speed
      <select id="speed">
        <option value="3">Slow</option><option value="10">Normal</option><option value="40" selected>Fast</option>
        <option value="150">Faster</option><option value="600">Very fast</option><option value="2500">Blazing</option>
      </select></label>
    <button id="recbtn" title="Save the replay as a short video you can send on Discord">Record video</button>
    <label class="chk">Skin <select id="skin"></select></label>
    <span id="skincols" style="display:none" class="chk"><input type="color" id="skinbody" title="Body colour"><input type="color" id="skinaccent" title="Accent colour"></span>
    <label class="chk"><input type="checkbox" id="tex" checked>Textures</label>
    <label class="chk"><input type="checkbox" id="follow" checked>Follow turtle</label>
    <span id="layerbox">Layers 1&ndash;<b id="layerval"></b><input type="range" id="layer" min="1" max="1" value="1" step="1"></span>
  </div>
</div>
<div id="fail" class="card"></div>
<div id="recbadge" class="card"><b>&#9679; REC</b><span id="rectime">0s</span><button id="reccancel">Cancel</button></div>
<div id="recpanel">
  <div class="card">
    <h3>Save as a video</h3>
    <div id="recform">
      <div class="row">Length
        <select id="reclen"><option value="10">10 seconds</option><option value="20">20 seconds</option>
          <option value="30" selected>30 seconds</option><option value="45">45 seconds</option><option value="60">60 seconds</option></select></div>
      <div class="row">File size
        <select id="recmb"><option value="9" selected>Fits Discord (under 10 MB)</option><option value="24">Better quality (up to 25 MB)</option>
          <option value="48">Highest quality (up to 50 MB)</option></select></div>
      <div class="row">The whole route is sped up to fit the length, and the camera slowly circles the build.</div>
      <div class="note">Keep this tab open and in front while it records. It plays once in real time, so a 30 second video takes 30 seconds.</div>
      <div class="row" style="justify-content:flex-end"><button id="recclose">Close</button><button id="recstart" class="primary">Start recording</button></div>
    </div>
    <div id="recresult" style="display:none"></div>
  </div>
</div>

<script>@@THREE@@</script>
<script>@@TURTLE3D@@</script>
<script>
"use strict";
var DATA = @@DATA@@;
(function () {
  var D = DATA, W = D.w, DEP = D.d, H = D.h;
  var $ = function (id) { return document.getElementById(id); };
  var FACE_NAMES = ["", "forward", "right", "back", "left"];
  var FACE_YAW = [0, 0, -Math.PI / 2, Math.PI, Math.PI / 2];
  var SECONDS_PER_ACTION = 0.4;

  $("title").textContent = D.name;
  if (D.share) {
    $("sharebar").style.display = "";
    $("sh-gallery").href = D.share.gallery;
    $("sh-file").href = D.share.design;
    $("sh-file").setAttribute("download", D.share.slug + ".json");
    $("sh-note").textContent = "To dig this: type  " + D.share.cmd + "  on a turtle with the Carve menu installed. " +
      "To edit it, open Carve Designer and use  Open from link  with this page's address.";
    $("sh-copy").onclick = function () {
      var t = D.share.cmd;
      var ok = function () { $("sh-copy").textContent = "Copied!"; setTimeout(function () { $("sh-copy").textContent = "Copy turtle command"; }, 1500); };
      if (navigator.clipboard && navigator.clipboard.writeText) navigator.clipboard.writeText(t).then(ok, function () {});
      else { var a = document.createElement("textarea"); a.value = t; document.body.appendChild(a); a.select(); try { document.execCommand("copy"); ok(); } catch (e) {} a.remove(); }
    };
  }
  $("sub").textContent = D.pattern + "  ·  torches: " + D.torches + "  ·  " + W + " × " + DEP + " × " + H;

  var canvas = $("c"), renderer;
  try {
    renderer = new THREE.WebGLRenderer({ canvas: canvas, antialias: true });
  } catch (e) {
    var f = $("fail"); f.style.display = "flex";
    f.textContent = "This page needs WebGL, and your browser or device has it turned off.";
    return;
  }
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
  renderer.setClearColor(0x14171a);
  var scene = new THREE.Scene();
  var camera = new THREE.PerspectiveCamera(45, 1, 0.1, 2000);
  scene.add(new THREE.AmbientLight(0xffffff, 0.62));
  var sun = new THREE.DirectionalLight(0xffffff, 0.85);
  sun.position.set(0.6, 1, 0.8);
  scene.add(sun);
  var clip = new THREE.Plane(new THREE.Vector3(0, -1, 0), H + 0.5);
  renderer.clippingPlanes = [clip];

  // three uses (x, y, -z): x right, y up, -z forward
  function P(x, y, z) { return new THREE.Vector3(x, y, -z); }
  function key(x, y, z) { return x + 256 * (z + 256 * y); }

  // ---- the box
  var cx = (W + 1) / 2, cy = (H + 1) / 2, cz = -(DEP + 1) / 2;
  var edges = new THREE.LineSegments(new THREE.EdgesGeometry(new THREE.BoxGeometry(W, H, DEP)),
                                     new THREE.LineBasicMaterial({ color: 0x4a525b }));
  edges.position.set(cx, cy, cz);
  scene.add(edges);
  var gsize = Math.max(W, DEP) + 6;
  var grid = new THREE.GridHelper(gsize, gsize, 0x2c333a, 0x23292f);
  grid.position.set(cx, 0.5, cz);
  scene.add(grid);

  // ---- cells that get dug
  var sel = D.sel, nSel = sel.length / 3;
  var start = D.turtle;
  var events = D.events, nEv = events.length / 4;
  var dugEver = {};
  dugEver[key(start[0], start[1], start[2])] = true;
  for (var i = 0; i < nEv; i++) if (events[4 * i] === 1) dugEver[key(events[4 * i + 1], events[4 * i + 2], events[4 * i + 3])] = true;
  var digIdx = {}, skipCells = [], digCells = [];
  for (i = 0; i < nSel; i++) {
    var sx = sel[3 * i], sy = sel[3 * i + 1], sz = sel[3 * i + 2], k = key(sx, sy, sz);
    if (dugEver[k]) { digIdx[k] = digCells.length; digCells.push([sx, sy, sz]); } else skipCells.push([sx, sy, sz]);
  }
  var boxGeo = new THREE.BoxGeometry(0.94, 0.94, 0.94);
  var dummy = new THREE.Object3D(), ZERO = new THREE.Matrix4().makeScale(0, 0, 0), col = new THREE.Color();
  var digMesh = new THREE.InstancedMesh(boxGeo, new THREE.MeshLambertMaterial({ color: 0xffffff }), Math.max(1, digCells.length));
  var seed = 12345;
  function rnd() { seed = (seed * 1103515245 + 12345) & 0x7fffffff; return seed / 0x7fffffff; }
  var digMat = [], rainbow = [], neutral = [];
  for (i = 0; i < digCells.length; i++) {
    var c = digCells[i];
    dummy.position.copy(P(c[0], c[1], c[2])); dummy.scale.set(1, 1, 1); dummy.updateMatrix();
    digMat.push(dummy.matrix.clone());
    digMesh.setMatrixAt(i, dummy.matrix);
    col.setHSL(0.08 + 0.5 * (H > 1 ? (c[1] - 1) / (H - 1) : 0), 0.62, 0.5 + (rnd() - 0.5) * 0.1);
    rainbow.push(col.clone());
    var sh = 0.86 + rnd() * 0.14;
    neutral.push(new THREE.Color(sh, sh, sh));
    digMesh.setColorAt(i, col);
  }
  scene.add(digMesh);

  var skipMesh = null;
  if (skipCells.length) {
    skipMesh = new THREE.InstancedMesh(boxGeo, new THREE.MeshLambertMaterial({ color: 0xd9534f, transparent: true, opacity: 0.45 }), skipCells.length);
    for (i = 0; i < skipCells.length; i++) {
      var s = skipCells[i];
      dummy.position.copy(P(s[0], s[1], s[2])); dummy.scale.set(1, 1, 1); dummy.updateMatrix();
      skipMesh.setMatrixAt(i, dummy.matrix);
    }
    scene.add(skipMesh);
  } else $("lg-skip").style.display = "none";

  // ---- blocks and torches the turtle places (one mesh per item, drawn with our simplified tile)
  var place = D.place, nPl = place.length / 4;
  var groups = {}, torches = [], plIdx = {};
  for (i = 0; i < nPl; i++) {
    var slot = place[4 * i + 3], item = D.inv[slot] || "";
    var pk = key(place[4 * i], place[4 * i + 1], place[4 * i + 2]);
    if (item.indexOf("torch") >= 0) { plIdx[pk] = { torch: true, n: torches.length }; torches.push(i); }
    else {
      var gr = groups[slot] || (groups[slot] = { list: [], mats: [] });
      plIdx[pk] = { torch: false, slot: slot, n: gr.list.length }; gr.list.push(i);
    }
  }
  function makeTexture(rows) {
    var cv = document.createElement("canvas"); cv.width = cv.height = 16;
    var cx = cv.getContext("2d");
    for (var y = 0; y < 16; y++) for (var x = 0; x < 16; x++) {
      var hx = rows[y][x]; if (hx !== "-") { cx.fillStyle = "#" + hx; cx.fillRect(x, y, 1, 1); }
    }
    var t = new THREE.CanvasTexture(cv); t.magFilter = THREE.NearestFilter; t.minFilter = THREE.NearestFilter;
    return t;
  }
  var blockGeo = new THREE.BoxGeometry(0.9, 0.9, 0.9), nBlocks = 0;
  Object.keys(groups).forEach(function (slot) {
    var gr = groups[slot], tile = D.tiles && D.tiles[slot];
    gr.matFlat = new THREE.MeshLambertMaterial({ color: new THREE.Color(D.colors[slot] || "#9aa0a6") });
    gr.matTex = tile ? new THREE.MeshLambertMaterial({ map: makeTexture(tile), alphaTest: 0.5 }) : gr.matFlat;
    gr.mesh = new THREE.InstancedMesh(blockGeo, gr.matTex, gr.list.length);
    for (var j = 0; j < gr.list.length; j++) {
      var p = gr.list[j];
      dummy.position.copy(P(place[4 * p], place[4 * p + 1], place[4 * p + 2])); dummy.scale.set(1, 1, 1); dummy.updateMatrix();
      gr.mats.push(dummy.matrix.clone());
      gr.mesh.setMatrixAt(j, ZERO);
    }
    scene.add(gr.mesh); nBlocks += gr.list.length;
  });
  var torchMesh = new THREE.InstancedMesh(new THREE.BoxGeometry(0.2, 0.62, 0.2),
                     new THREE.MeshBasicMaterial({ color: 0xffe070 }), Math.max(1, torches.length));
  var torchMat = [];
  for (i = 0; i < torches.length; i++) {
    var tp = torches[i];
    dummy.position.copy(P(place[4 * tp], place[4 * tp + 1] - 0.12, place[4 * tp + 2])); dummy.scale.set(1, 1, 1); dummy.updateMatrix();
    torchMat.push(dummy.matrix.clone()); torchMesh.setMatrixAt(i, ZERO);
  }
  scene.add(torchMesh);
  if (!nPl) $("lg-place").style.display = "none";

  // ---- chest, turtle, trail
  if (D.chest) {
    var chest = new THREE.Mesh(new THREE.BoxGeometry(0.85, 0.75, 0.85), new THREE.MeshLambertMaterial({ color: 0xa0682d }));
    chest.position.copy(P(D.chest[0], D.chest[1] - 0.06, D.chest[2]));
    scene.add(chest);
  } else $("lg-chest").style.display = "none";

  // ---- the turtle and its skins. Every skin is built from boxes and faces -Z (the direction the turtle looks).
  var turtle = new THREE.Group();
  scene.add(turtle);
  var SKIN_LIST = [["crafty", "Crafty turtle"], ["classic", "Green turtle"], ["bee", "Bee"], ["sea", "Sea turtle"], ["golem", "Iron golem"], ["custom", "Custom colours"]];
  var SKIN_COLOR = { crafty: "#aab0ba", classic: "#6fe36f", bee: "#f5c518", sea: "#3a9d5a", golem: "#c9c9c4" };
  var skinState = { name: D.skin || "crafty", body: D.skinBody || "#6fe36f", accent: D.skinAccent || "#1c7c3c" };
  var skinTick = function () {};
  function MAT(c, basic) { return basic ? new THREE.MeshBasicMaterial({ color: c }) : new THREE.MeshLambertMaterial({ color: c }); }
  function BOX(g, w, h, d, c, x, y, z, basic) {
    var m = new THREE.Mesh(new THREE.BoxGeometry(w, h, d), MAT(c, basic));
    m.position.set(x, y, z); g.add(m); return m;
  }
  function shade(hex, f) {
    var c = new THREE.Color(hex); c.multiplyScalar(f); return "#" + c.getHexString();
  }
  // the turtle body every "same shape" skin shares: a cube with a face plate and a pickaxe on its right side
  function turtleBody(g, body, accent, plate) {
    BOX(g, 0.78, 0.7, 0.78, body, 0, 0, 0);
    BOX(g, 0.8, 0.1, 0.8, shade(body, 0.7), 0, -0.3, 0);
    BOX(g, 0.5, 0.04, 0.5, shade(body, 1.18), 0, 0.37, 0.05);
    BOX(g, 0.34, 0.34, 0.3, accent, 0, 0, -0.52);
    BOX(g, 0.62, 0.42, 0.04, plate || "#14301a", 0, 0.05, -0.4);
    BOX(g, 0.1, 0.1, 0.05, "#f4f4f4", -0.17, 0.12, -0.425, true);
    BOX(g, 0.1, 0.1, 0.05, "#f4f4f4", 0.17, 0.12, -0.425, true);
    BOX(g, 0.05, 0.07, 0.05, "#101316", -0.17, 0.12, -0.45, true);
    BOX(g, 0.05, 0.07, 0.05, "#101316", 0.17, 0.12, -0.45, true);
    BOX(g, 0.2, 0.03, 0.05, "#101316", 0, -0.06, -0.42, true);
    // pickaxe
    var pick = new THREE.Group();
    BOX(pick, 0.05, 0.5, 0.05, "#7a5230", 0, 0, 0);
    BOX(pick, 0.05, 0.08, 0.34, "#9fb7c4", 0, 0.24, 0);
    pick.position.set(0.5, 0.05, -0.12); pick.rotation.x = -0.5;
    g.add(pick);
    return pick;
  }
  var SKIN_BUILD = {
    crafty: function (g) {
      var m = CarveTurtle.make(THREE, D.skinSeed || 0);
      m.position.y = 0.05; g.add(m);
      return function () {};
    },
    classic: function (g) { turtleBody(g, "#6fe36f", "#1c7c3c"); return function () {}; },
    custom: function (g) { turtleBody(g, skinState.body, skinState.accent); return function () {}; },
    bee: function (g) {
      var yellow = "#f6c21c", black = "#1d1a14";
      turtleBody(g, yellow, black, "#2a2418");
      [-0.24, 0.02, 0.28].forEach(function (z) {          // the stripes
        BOX(g, 0.8, 0.72, 0.1, black, 0, 0, z);
      });
      BOX(g, 0.04, 0.2, 0.04, black, -0.1, 0.45, -0.5); BOX(g, 0.04, 0.2, 0.04, black, 0.1, 0.45, -0.5);       // antennae
      BOX(g, 0.09, 0.07, 0.09, "#f6c21c", -0.1, 0.57, -0.5); BOX(g, 0.09, 0.07, 0.09, "#f6c21c", 0.1, 0.57, -0.5);
      BOX(g, 0.1, 0.1, 0.16, black, 0, -0.05, 0.47);                                                           // stinger
      var wl = new THREE.Group(), wr = new THREE.Group();
      var wmat = function () { return new THREE.MeshBasicMaterial({ color: 0xd8f2ff, transparent: true, opacity: 0.62, side: THREE.DoubleSide }); };
      var w1 = new THREE.Mesh(new THREE.BoxGeometry(0.46, 0.02, 0.34), wmat()); w1.position.set(-0.25, 0, 0);
      var w2 = new THREE.Mesh(new THREE.BoxGeometry(0.46, 0.02, 0.34), wmat()); w2.position.set(0.25, 0, 0);
      wl.add(w1); wr.add(w2); wl.position.set(-0.08, 0.4, 0.1); wr.position.set(0.08, 0.4, 0.1);
      g.add(wl, wr);
      return function (t) { var a = Math.sin(t * 38) * 0.45; wl.rotation.z = 0.25 + a; wr.rotation.z = -0.25 - a; };
    },
    sea: function (g) {
      var shell = "#5c8a3a", shellHi = "#78a84a", shellLo = "#3f6428", skin = "#86b552", belly = "#d9d08a";
      var s = new THREE.Group();
      BOX(s, 0.78, 0.07, 0.96, belly, 0, -0.17, 0.02);
      BOX(s, 0.92, 0.17, 1.0, shellLo, 0, -0.07, 0.02);
      BOX(s, 0.76, 0.15, 0.84, shell, 0, 0.07, 0.02);
      BOX(s, 0.5, 0.13, 0.58, shellHi, 0, 0.19, 0.0);
      BOX(s, 0.26, 0.09, 0.3, shell, 0, 0.28, -0.02);
      [[-0.2, 0.2], [0.2, 0.2], [-0.2, -0.17], [0.2, -0.17]].forEach(function (p) {      // scutes
        BOX(s, 0.17, 0.02, 0.17, shellLo, p[0], 0.27 - Math.abs(p[0]) * 0.1, p[1] * 0.95);
      });
      BOX(s, 0.08, 0.02, 0.6, shellLo, 0, 0.33, -0.02);
      var head = new THREE.Group();
      BOX(head, 0.3, 0.24, 0.32, skin, 0, 0, 0);
      BOX(head, 0.2, 0.06, 0.1, shade(skin, 0.8), 0, -0.06, -0.19);
      BOX(head, 0.06, 0.06, 0.04, "#101316", -0.1, 0.05, -0.17, true); BOX(head, 0.06, 0.06, 0.04, "#101316", 0.1, 0.05, -0.17, true);
      head.position.set(0, -0.04, -0.62);
      s.add(head);
      BOX(s, 0.14, 0.05, 0.24, skin, 0, -0.05, 0.58);                                    // tail
      var flips = [];
      [[-1, -0.22, 0.46, 0.2, 0.74], [1, -0.22, 0.46, 0.2, 0.74], [-1, 0.4, 0.28, 0.2, 0.55], [1, 0.4, 0.28, 0.2, 0.55]].forEach(function (f) {
        var fl = new THREE.Group();
        BOX(fl, f[2], 0.06, f[3], skin, f[0] * f[2] / 2, 0, 0);
        BOX(fl, f[2] * 0.4, 0.07, f[3] * 0.9, shade(skin, 0.82), f[0] * f[2] * 0.8, 0, 0);
        fl.position.set(f[0] * 0.42, -0.12, f[1]);
        s.add(fl); flips.push([fl, f[0], f[1] < 0 ? 0 : 1.6]);
      });
      s.scale.setScalar(0.8);
      g.add(s);
      return function (t) {
        flips.forEach(function (f) { f[0].rotation.z = f[1] * (0.18 + 0.2 * Math.sin(t * 5 + f[2])); });
        head.position.z = -0.62 - 0.02 * Math.sin(t * 2.5);
      };
    },
    golem: function (g) {
      var iron = "#9a968f", ironLo = "#76726d", ironHi = "#aeaaa3", vine = "#4f8a3a", nose = "#8f6b4f";
      var k = 0.025, y0 = -0.46;
      var gg = new THREE.Group();
      function px(w, h, d, c, x, y, z) { return BOX(gg, w * k, h * k, d * k, c, x * k, y0 + y * k, z * k); }
      px(6, 13, 5, ironLo, -5, 6.5, 0); px(6, 13, 5, ironLo, 5, 6.5, 0);                     // legs
      px(9, 5, 6, iron, 0, 15.5, 0);                                                         // waist
      px(18, 12, 11, iron, 0, 24, 0);                                                        // chest
      px(18, 4, 11.4, ironHi, 0, 28, 0);
      px(8, 10, 8, iron, 0, 35, -0.5);                                                       // head
      px(2, 4, 2, nose, 0, 33, -5.5);                                                        // nose
      px(2.2, 1.6, 1, "#241f1c", -2.4, 36, -4.7); px(2.2, 1.6, 1, "#241f1c", 2.4, 36, -4.7);  // eyes
      px(8.4, 1.4, 1, ironLo, 0, 37.6, -4.7);                                                // brow
      px(6, 3, 0.8, vine, -3, 22, -5.8); px(2, 6, 0.8, vine, 4, 20, -5.8); px(4, 2, 0.8, vine, 5, 27, -5.8);   // vines
      var armL = new THREE.Group(), armR = new THREE.Group();
      [[armL, -1], [armR, 1]].forEach(function (a) {
        var m = new THREE.Mesh(new THREE.BoxGeometry(4 * k, 26 * k, 6 * k), MAT(iron)); m.position.y = -13 * k; a[0].add(m);
        var v = new THREE.Mesh(new THREE.BoxGeometry(4.4 * k, 6 * k, 6.4 * k), MAT(vine)); v.position.y = -7 * k; if (a[1] > 0) a[0].add(v);
        a[0].position.set(a[1] * 11 * k, y0 + 30 * k, 0); gg.add(a[0]);
      });
      g.add(gg);
      return function (t) {
        var sw = 0.07 * Math.sin(t * 3);
        armL.rotation.x = sw; armR.rotation.x = -sw;
      };
    }
  };
  function setSkin(name) {
    if (!SKIN_BUILD[name]) name = "crafty";
    skinState.name = name;
    for (var i = turtle.children.length - 1; i >= 0; i--) {
      var ch = turtle.children[i]; turtle.remove(ch);
      ch.traverse(function (o) { if (o.geometry) o.geometry.dispose(); if (o.material) o.material.dispose(); });
    }
    var g = new THREE.Group();
    skinTick = SKIN_BUILD[name](g) || function () {};
    turtle.add(g);
    var sw = $("skin"); if (sw && sw.value !== name) sw.value = name;
    var cc = $("skincols"); if (cc) cc.style.display = name === "custom" ? "" : "none";
    var lg = $("lg-turtle"); if (lg) lg.style.background = name === "custom" ? skinState.body : SKIN_COLOR[name];
  }
  (function () {
    var sw = $("skin");
    if (sw) {
      SKIN_LIST.forEach(function (s) { var o = document.createElement("option"); o.value = s[0]; o.textContent = s[1]; sw.appendChild(o); });
      sw.onchange = function () { setSkin(sw.value); };
    }
    var cb = $("skinbody"), ca = $("skinaccent");
    if (cb) { cb.value = skinState.body; cb.oninput = function () { skinState.body = cb.value; if (skinState.name === "custom") setSkin("custom"); }; }
    if (ca) { ca.value = skinState.accent; ca.oninput = function () { skinState.accent = ca.value; if (skinState.name === "custom") setSkin("custom"); }; }
    var m = /[#&]skin=(\w+)/.exec(location.hash);
    setSkin(m ? m[1] : skinState.name);
  })();
  var TRAIL = 220, trailPts = [], trailGeo = new THREE.BufferGeometry();
  trailGeo.setAttribute("position", new THREE.BufferAttribute(new Float32Array(TRAIL * 3), 3));
  var trail = new THREE.Line(trailGeo, new THREE.LineBasicMaterial({ color: 0x5ad1e6 }));
  trail.frustumCulled = false;
  scene.add(trail);
  var puffs = [];
  var puffGeo = new THREE.BoxGeometry(1, 1, 1);
  function puff(x, y, z) {
    var m = new THREE.Mesh(puffGeo, new THREE.MeshBasicMaterial({ color: 0xffffff, transparent: true, opacity: 0.7 }));
    m.position.copy(P(x, y, z)); scene.add(m); puffs.push({ m: m, t: 0 });
    if (puffs.length > 60) { var o = puffs.shift(); scene.remove(o.m); o.m.material.dispose(); }
  }

  // ---- simulation state
  var cur = 0, pos = start.slice(), face = 1, moves = 0, turns = 0, digs = 0, placed = 0, dirty = false;
  var vis = P(pos[0], pos[1], pos[2]), visYaw = FACE_YAW[1], playing = false, acc = 0, lastStepWasLive = false;

  function setTrail() {
    var a = trailGeo.attributes.position.array;
    for (var j = 0; j < trailPts.length; j++) { a[3 * j] = trailPts[j].x; a[3 * j + 1] = trailPts[j].y; a[3 * j + 2] = trailPts[j].z; }
    trailGeo.setDrawRange(0, trailPts.length); trailGeo.attributes.position.needsUpdate = true;
  }
  function reset() {
    cur = 0; pos = start.slice(); face = 1; moves = turns = digs = placed = 0;
    for (var j = 0; j < digCells.length; j++) digMesh.setMatrixAt(j, digMat[j]);
    var sk = digIdx[key(start[0], start[1], start[2])];
    if (sk !== undefined) digMesh.setMatrixAt(sk, ZERO);
    Object.keys(groups).forEach(function (sl) { for (var q = 0; q < groups[sl].list.length; q++) groups[sl].mesh.setMatrixAt(q, ZERO); });
    for (j = 0; j < torches.length; j++) torchMesh.setMatrixAt(j, ZERO);
    trailPts = [P(pos[0], pos[1], pos[2])]; setTrail();
    dirty = true;
  }
  function step(live) {
    var b = 4 * cur, t = events[b], x = events[b + 1], y = events[b + 2], z = events[b + 3];
    if (t === 0) { face = x; turns++; }
    else if (t === 1) {
      var di = digIdx[key(x, y, z)];
      if (di !== undefined) digMesh.setMatrixAt(di, ZERO);
      digs++; dirty = true; if (live) puff(x, y, z);
    } else if (t === 2) {
      pos = [x, y, z]; moves++;
      trailPts.push(P(x, y, z)); if (trailPts.length > TRAIL) trailPts.shift();
    } else {
      var pi = plIdx[key(x, y, z)];
      if (pi) {
        if (pi.torch) torchMesh.setMatrixAt(pi.n, torchMat[pi.n]); else groups[pi.slot].mesh.setMatrixAt(pi.n, groups[pi.slot].mats[pi.n]);
        dirty = true;
      }
      placed++;
    }
    cur++;
  }
  function seek(n) {
    n = Math.max(0, Math.min(nEv, n));
    if (n < cur) reset();
    while (cur < n) step(false);
    setTrail(); dirty = true; snapTurtle();
  }
  function snapTurtle() {
    vis.copy(P(pos[0], pos[1], pos[2])); visYaw = FACE_YAW[face];
  }

  // ---- camera (orbit)
  var target = new THREE.Vector3(cx, cy, cz), tgt = target.clone();
  var span = Math.max(W, DEP, H);
  var radius = span * 1.9 + 4, theta = 0.55, phi = 1.05;
  function placeCamera() {
    var sp = Math.sin(phi);
    camera.position.set(target.x + radius * sp * Math.sin(theta), target.y + radius * Math.cos(phi), target.z + radius * sp * Math.cos(theta));
    camera.lookAt(target);
  }
  var ptrs = {}, lastPinch = 0;
  canvas.addEventListener("contextmenu", function (e) { e.preventDefault(); });
  canvas.addEventListener("pointerdown", function (e) {
    canvas.setPointerCapture(e.pointerId); ptrs[e.pointerId] = { x: e.clientX, y: e.clientY, b: e.button, sh: e.shiftKey };
    canvas.classList.add("drag"); lastPinch = 0;
  });
  canvas.addEventListener("pointerup", function (e) { delete ptrs[e.pointerId]; canvas.classList.remove("drag"); });
  canvas.addEventListener("pointercancel", function (e) { delete ptrs[e.pointerId]; canvas.classList.remove("drag"); });
  canvas.addEventListener("pointermove", function (e) {
    var p = ptrs[e.pointerId]; if (!p) return;
    var dx = e.clientX - p.x, dy = e.clientY - p.y, ids = Object.keys(ptrs);
    if (ids.length >= 2) {
      var a = ptrs[ids[0]], b = ptrs[ids[1]];
      var np = { x: e.clientX, y: e.clientY };
      var o = e.pointerId == ids[0] ? b : a, me = e.pointerId == ids[0] ? a : b;
      var before = Math.hypot(me.x - o.x, me.y - o.y), after = Math.hypot(np.x - o.x, np.y - o.y);
      if (before > 0) radius = Math.max(3, Math.min(600, radius * before / Math.max(after, 1)));
      p.x = e.clientX; p.y = e.clientY; return;
    }
    p.x = e.clientX; p.y = e.clientY;
    if (p.b === 2 || p.b === 1 || p.sh) {
      var k = radius * 0.0016, right = new THREE.Vector3(), up = new THREE.Vector3();
      camera.matrix.extractBasis(right, up, new THREE.Vector3());
      tgt.addScaledVector(right, -dx * k).addScaledVector(up, dy * k);
      $("follow").checked = false;
    } else {
      theta -= dx * 0.008; phi = Math.max(0.08, Math.min(Math.PI - 0.08, phi - dy * 0.008));
    }
  });
  canvas.addEventListener("wheel", function (e) {
    e.preventDefault(); radius = Math.max(3, Math.min(600, radius * Math.exp(e.deltaY * 0.001)));
  }, { passive: false });

  // ---- look: rainbow layer colours + flat colours, or textures
  var digTex = D.digTile ? makeTexture(D.digTile) : null;
  function applyLook() {
    var on = $("tex").checked;
    digMesh.material.map = on && digTex ? digTex : null;
    digMesh.material.needsUpdate = true;
    for (var q = 0; q < digCells.length; q++) digMesh.setColorAt(q, on && digTex ? neutral[q] : rainbow[q]);
    digMesh.instanceColor.needsUpdate = true;
    Object.keys(groups).forEach(function (sl) { groups[sl].mesh.material = on ? groups[sl].matTex : groups[sl].matFlat; });
    $("lg-dig").innerHTML = on && digTex ? "<i style=\"background:#7d8590\"></i>to dig" : "<i style=\"background:linear-gradient(90deg,#f0a030,#4fd37a,#3b8fe8)\"></i>to dig (colour = layer)";
  }
  $("tex").onchange = applyLook;
  if (!digTex && !Object.keys(D.tiles || {}).length) $("tex").parentNode.style.display = "none";
  applyLook();

  // ---- controls
  var seekEl = $("seek"), playBtn = $("play"), speedEl = $("speed"), layerEl = $("layer");
  seekEl.max = nEv; layerEl.max = H; layerEl.value = H; $("layerval").textContent = H;
  if (H < 2) $("layerbox").style.display = "none";
  function setPlaying(on) {
    if (on && cur >= nEv) { seek(0); }
    playing = on; playBtn.textContent = on ? "Pause" : (cur >= nEv ? "Replay" : "Play");
  }
  playBtn.onclick = function () { setPlaying(!playing); };
  $("reset").onclick = function () { setPlaying(false); seek(0); playBtn.textContent = "Play"; };
  $("fwd").onclick = function () { setPlaying(false); seek(cur + 1); };
  $("back").onclick = function () { setPlaying(false); seek(cur - 1); };
  seekEl.oninput = function () { setPlaying(false); seek(parseInt(seekEl.value, 10)); };
  layerEl.oninput = function () { var v = parseInt(layerEl.value, 10); clip.constant = v + 0.5; $("layerval").textContent = v; };
  window.addEventListener("keydown", function (e) {
    if (e.target && e.target.tagName === "SELECT") return;
    if (e.code === "Space") { e.preventDefault(); setPlaying(!playing); }
    else if (e.code === "ArrowRight") { setPlaying(false); seek(cur + (e.shiftKey ? 25 : 1)); }
    else if (e.code === "ArrowLeft") { setPlaying(false); seek(cur - (e.shiftKey ? 25 : 1)); }
  });

  function fmtTime(s) {
    s = Math.round(s); var h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), r = s % 60;
    return (h ? h + "h " : "") + (h || m ? m + "m " : "") + r + "s";
  }
  var totalDig = digCells.length, lastHud = 0;
  function hud() {
    var secs = (moves + digs + turns + placed) * SECONDS_PER_ACTION, all = D.seconds;
    var rows = [["Dug", digs + " / " + totalDig + (skipCells.length ? "  (" + skipCells.length + " skipped)" : "")]];
    if (nPl) rows.push(["Placed", placed + " / " + nPl]);
    rows.push(["Moves", moves + " / " + D.moves], ["Turns", String(turns)],
              ["Game time", fmtTime(secs) + " / " + fmtTime(all)],
              ["Turtle", "x" + pos[0] + " y" + pos[1] + " z" + pos[2] + " " + FACE_NAMES[face]]);
    $("stats").innerHTML = rows.map(function (r) { return "<span>" + r[0] + "</span><span>" + r[1] + "</span>"; }).join("");
    seekEl.value = cur; $("pct").textContent = (nEv ? Math.floor(100 * cur / nEv) : 100) + "%";
    if (!playing) playBtn.textContent = cur >= nEv && nEv ? "Replay" : "Play";
  }

  function resize() {
    if (recState) return;
    var w = window.innerWidth, h = window.innerHeight;
    renderer.setSize(w, h, false); camera.aspect = w / h; camera.updateProjectionMatrix();
  }
  window.addEventListener("resize", resize); resize();

  // ---- recording a video of the replay (canvas -> MediaRecorder)
  var recState = null, recHud = null;
  function pickMime() {
    if (!window.MediaRecorder) return "";
    var c = ["video/mp4;codecs=avc1.42E01E", "video/mp4", "video/webm;codecs=vp9", "video/webm;codecs=vp8", "video/webm"];
    for (var i = 0; i < c.length; i++) if (MediaRecorder.isTypeSupported(c[i])) return c[i];
    return "";
  }
  function drawComposite() {
    var R = recState, c = R.ctx, W2 = R.W, H2 = R.H;
    c.drawImage(canvas, 0, 0, W2, H2);
    var u = H2 / 720;
    c.fillStyle = "rgba(20,23,26,0.74)"; c.fillRect(16 * u, 16 * u, 500 * u, 64 * u);
    c.fillStyle = "#e6edf3"; c.font = "600 " + (22 * u) + "px system-ui, sans-serif"; c.textBaseline = "top";
    c.fillText(D.name, 28 * u, 24 * u);
    c.fillStyle = "#8b949e"; c.font = (14 * u) + "px system-ui, sans-serif";
    c.fillText(D.pattern + "  \u00b7  " + W + " \u00d7 " + DEP + " \u00d7 " + H, 28 * u, 54 * u);
    var line = "Dug " + digs + " / " + totalDig + (nPl ? "     Placed " + placed + " / " + nPl : "");
    c.font = "600 " + (18 * u) + "px system-ui, sans-serif";
    var tw = c.measureText(line).width + 32 * u;
    c.fillStyle = "rgba(20,23,26,0.74)"; c.fillRect(W2 - 16 * u - tw, 16 * u, tw, 44 * u);
    c.fillStyle = "#e6edf3"; c.fillText(line, W2 - 16 * u - tw + 16 * u, 27 * u);
    var frac = nEv ? cur / nEv : 1;
    c.fillStyle = "rgba(20,23,26,0.74)"; c.fillRect(16 * u, H2 - 30 * u, W2 - 32 * u, 14 * u);
    c.fillStyle = "#f0a030"; c.fillRect(18 * u, H2 - 28 * u, (W2 - 36 * u) * frac, 10 * u);
    c.fillStyle = "rgba(230,237,243,0.7)"; c.font = (13 * u) + "px system-ui, sans-serif";
    var mk = "Made with Carve Designer"; c.fillText(mk, W2 - 16 * u - c.measureText(mk).width, H2 - 52 * u);
  }
  function recTick(now) {
    var R = recState, t = (now - R.t0) / 1000;
    var want = t < R.intro ? 0 : Math.min(nEv, Math.floor(nEv * Math.min(1, (t - R.intro) / R.playSec)));
    var moved = 0;
    while (cur < want) { step(R.speed < 60); moved++; }
    if (moved) setTrail();
    theta = R.theta0 + t * R.spin;
    R.t = t;
  }
  function recordVideo(o) {
    return new Promise(function (resolve, reject) {
      var mime = pickMime();
      if (!mime) { reject(new Error("This browser can't record video. Try Chrome, Edge or Firefox.")); return; }
      var T = Math.max(3, o.seconds || 30), W2 = o.width || 1280, H2 = Math.round(W2 * 9 / 16);
      var bps = Math.max(300000, Math.min(16000000, Math.floor((o.mb || 9) * 8e6 * 0.9 / T)));
      setPlaying(false); seek(0);
      var comp = document.createElement("canvas"); comp.width = W2; comp.height = H2;
      var stream = comp.captureStream(30), chunks = [], mr;
      try { mr = new MediaRecorder(stream, { mimeType: mime, videoBitsPerSecond: bps }); }
      catch (e) { reject(e); return; }
      var wasFollow = $("follow").checked; $("follow").checked = false;
      document.body.classList.add("rec");
      renderer.setPixelRatio(1); renderer.setSize(W2, H2, false);
      camera.aspect = W2 / H2; camera.updateProjectionMatrix();
      target.set(cx, cy, cz); tgt.copy(target);
      var intro = 0.8, outro = 1.6, playSec = Math.max(1, T - intro - outro);
      recState = { ctx: comp.getContext("2d"), W: W2, H: H2, t0: performance.now(), T: T, intro: intro, playSec: playSec,
                   speed: nEv / playSec, theta0: theta, spin: 0.2, t: 0, cancelled: false };
      function cleanup() {
        recState = null; document.body.classList.remove("rec");
        renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2)); resize();
        $("follow").checked = wasFollow;
      }
      mr.ondataavailable = function (e) { if (e.data && e.data.size) chunks.push(e.data); };
      mr.onstop = function () {
        var cancelled = recState && recState.cancelled; cleanup();
        if (cancelled) { reject(new Error("cancelled")); return; }
        resolve({ blob: new Blob(chunks, { type: mime.split(";")[0] }), mime: mime.split(";")[0], bitrate: bps, seconds: T });
      };
      mr.start(500);
      recHud = setInterval(function () { if (recState) $("rectime").textContent = Math.min(T, Math.round(recState.t)) + " / " + T + " s"; }, 250);
      recState.stop = function (cancel) { if (cancel) recState.cancelled = true; try { mr.stop(); } catch (e) {} clearInterval(recHud); };
    });
  }
  function openRecPanel(on) { $("recpanel").classList.toggle("open", on); }
  $("recbtn").onclick = function () {
    setPlaying(false); $("recform").style.display = ""; $("recresult").style.display = "none"; $("recresult").innerHTML = "";
    if (!pickMime()) { $("recstart").disabled = true; $("recstart").textContent = "Not supported in this browser"; }
    openRecPanel(true);
  };
  $("recclose").onclick = function () { openRecPanel(false); };
  $("reccancel").onclick = function () { if (recState) recState.stop(true); };
  window.addEventListener("keydown", function (e) { if (e.code === "Escape" && recState) recState.stop(true); });
  $("recstart").onclick = function () {
    openRecPanel(false);
    recordVideo({ seconds: parseInt($("reclen").value, 10), mb: parseFloat($("recmb").value) }).then(function (r) {
      var url = URL.createObjectURL(r.blob), mb = r.blob.size / 1e6;
      var ext = r.mime === "video/mp4" ? "mp4" : "webm";
      var fname = (D.name || "carve").replace(/[^A-Za-z0-9_\-]+/g, "_") + "_turtle." + ext;
      $("recform").style.display = "none"; var out = $("recresult"); out.style.display = "";
      out.innerHTML = "<video controls loop autoplay muted playsinline src=\"" + url + "\"></video>" +
        "<div class=\"row\" style=\"justify-content:space-between\"><span>" + mb.toFixed(1) + " MB &middot; " + r.seconds + " s &middot; " + ext.toUpperCase() +
        "</span><span><a class=\"btn\" download=\"" + fname + "\" href=\"" + url + "\">Download video</a></span></div>" +
        "<div class=\"note\">" + (mb > 10 ? "That is over Discord's 10 MB limit for free accounts - record again with a shorter length or the 'Fits Discord' size. " : "Small enough to drop straight into Discord. ") +
        "</div><div class=\"row\" style=\"justify-content:flex-end\"><button id=\"recagain\">Record again</button><button id=\"recdone\">Close</button></div>";
      $("recagain").onclick = function () { $("recform").style.display = ""; out.style.display = "none"; };
      $("recdone").onclick = function () { openRecPanel(false); };
      openRecPanel(true);
    }, function (err) { if (err && err.message !== "cancelled") { alert("Could not record: " + err.message); } });
  };
  if (/(^|[#&])record/.test(location.hash)) { setTimeout(function () { $("recbtn").onclick(); }, 400); }

  reset(); setPlaying(false);
  var last = performance.now();
  function frame(now) {
    var dt = Math.min(0.1, (now - last) / 1000); last = now;
    if (recState) recTick(now);
    else if (playing) {
      var speed = parseFloat(speedEl.value);
      acc += dt * speed;
      var n = 0;
      while (acc >= 1 && cur < nEv) { step(speed <= 150); acc -= 1; n++; }
      if (n) setTrail();
      if (cur >= nEv) { setPlaying(false); acc = 0; }
    }
    if (dirty) {
      digMesh.instanceMatrix.needsUpdate = true; torchMesh.instanceMatrix.needsUpdate = true;
      Object.keys(groups).forEach(function (sl) { groups[sl].mesh.instanceMatrix.needsUpdate = true; });
      dirty = false;
    }
    var goal = P(pos[0], pos[1], pos[2]), k = 1 - Math.exp(-dt * (playing ? Math.max(8, parseFloat(speedEl.value) * 0.9) : 14));
    vis.lerp(goal, k);
    var yawGoal = FACE_YAW[face], dy = yawGoal - visYaw;
    dy = Math.atan2(Math.sin(dy), Math.cos(dy));
    visYaw += dy * (1 - Math.exp(-dt * 16));
    turtle.position.copy(vis); turtle.rotation.y = visYaw; skinTick(now / 1000);
    for (var j = puffs.length - 1; j >= 0; j--) {
      var pf = puffs[j]; pf.t += dt * 3.2;
      pf.m.scale.setScalar(1 - 0.7 * Math.min(1, pf.t)); pf.m.material.opacity = 0.7 * (1 - Math.min(1, pf.t));
      if (pf.t >= 1) { scene.remove(pf.m); pf.m.material.dispose(); puffs.splice(j, 1); }
    }
    if ($("follow").checked) tgt.copy(vis);
    target.lerp(tgt, 1 - Math.exp(-dt * 6));
    placeCamera();
    if (now - lastHud > 80 || !playing) { hud(); lastHud = now; }
    renderer.render(scene, camera);
    if (recState) {
      drawComposite();
      if (recState.t >= recState.T) recState.stop(false);
    }
    requestAnimationFrame(frame);
  }
  requestAnimationFrame(frame);
  window.CARVE_VIEWER = { setSkin: setSkin, skin: function () { return skinState.name; }, record: recordVideo, seek: seek, play: function () { setPlaying(true); }, state: function () {
    return { cur: cur, n: nEv, pos: pos, face: face, digs: digs, placed: placed, moves: moves, turns: turns, skipped: skipCells.length };
  } };
})();
</script>
</body>
</html>
'''
TURTLE3D_JS = r'''/* The Carve turtle model: a crafty turtle (grey cube, dark frame, chest / crafting-grid / slot faces). Shared by the 3D viewer and the Fleet map.
   It faces -Z. CarveTurtle.make(THREE, seed) gives every turtle its own hue (light pink, blue, mint...) with the same texture. */
var CarveTurtle = (function () {
  var FRAME = "#23252c", DARK = "#1b1d23";
  // a body colour per turtle; light, so the dark frame and icons stay readable
  var HUES = ["#f2b8d0", "#9fc4f2", "#a8e6c4", "#d2b8f2", "#f6cfa6", "#f2ec9c", "#92e0e0", "#f2a8a0", "#b8b8f4", "#c8e89c", "#e6b0e6", "#a8d8f6"];
  var cache = {};

  function hash(s) {
    var h = 0; s = String(s);
    for (var i = 0; i < s.length; i++) h = (h * 31 + s.charCodeAt(i)) | 0;
    return Math.abs(h);
  }
  function shade(hex, f) {
    var n = parseInt(hex.slice(1), 16), r = n >> 16, g = (n >> 8) & 255, b = n & 255;
    function c(v) { return Math.max(0, Math.min(255, Math.round(v * f))); }
    return "rgb(" + c(r) + "," + c(g) + "," + c(b) + ")";
  }
  // one 16x16 face drawn as big pixels
  function face(THREE, tint, draw) {
    var cv = document.createElement("canvas"); cv.width = cv.height = 64;
    var x = cv.getContext("2d"), K = 4;
    function R(c, a, b, w, h) { x.fillStyle = c; x.fillRect(a * K, b * K, w * K, h * K); }
    R(FRAME, 0, 0, 16, 16);
    R(shade(tint, 0.82), 1, 1, 14, 14);
    R(shade(tint, 1.0), 2, 2, 12, 12);
    R(shade(tint, 1.1), 2, 2, 12, 1); R(shade(tint, 1.1), 2, 2, 1, 12);
    R(shade(tint, 0.88), 2, 13, 12, 1); R(shade(tint, 0.88), 13, 2, 1, 12);
    if (draw) draw(R);
    var t = new THREE.CanvasTexture(cv);
    t.magFilter = THREE.NearestFilter; t.minFilter = THREE.NearestFilter;
    return t;
  }
  function frameBox(R, a, b, w, h) {                         // an outlined rectangle
    R(DARK, a, b, w, 1); R(DARK, a, b + h - 1, w, 1); R(DARK, a, b, 1, h); R(DARK, a + w - 1, b, 1, h);
  }
  function icons(THREE, t) {
    return {
      top: face(THREE, t, null),
      right: face(THREE, t, null),
      bottom: face(THREE, t, function (R) {                    // four nested squares
        [[2, 2], [8, 2], [2, 8], [8, 8]].forEach(function (p) {
          frameBox(R, p[0], p[1], 6, 6); frameBox(R, p[0] + 1, p[1] + 1, 4, 4); R(DARK, p[0] + 2, p[1] + 2, 2, 2);
        });
      }),
      front: face(THREE, t, function (R) {                     // the turtle's face: a wide slot, a little checker and a plus
        R(DARK, 3, 3, 10, 2); R(shade(t, 0.7), 3, 5, 10, 1);
        R(shade(t, 0.9), 2, 6, 12, 7);                                           // the lower plate, a touch darker
        [[3, 7], [5, 7], [4, 8], [3, 9], [5, 9]].forEach(function (p) { R(shade(t, 0.6), p[0] + 0.25, p[1] + 0.25, 1, 1); R("#fbfbff", p[0], p[1], 1, 1); });
        [[7, 10], [6, 11], [7, 11], [8, 11], [7, 12]].forEach(function (p) { R(shade(t, 0.6), p[0] + 0.25, p[1] + 0.25, 1, 1); R("#fbfbff", p[0], p[1], 1, 1); });
      }),
      back: face(THREE, t, function (R) {                      // a chest and a little slot
        frameBox(R, 3, 3, 10, 8); R(DARK, 3, 6, 10, 1); R(DARK, 7, 5, 2, 3); R(DARK, 10, 12, 4, 2);
      }),
      left: face(THREE, t, function (R) {                      // the crafting grid
        frameBox(R, 3, 3, 10, 10); frameBox(R, 4, 4, 8, 8); R(DARK, 6, 4, 1, 8); R(DARK, 9, 4, 1, 8); R(DARK, 4, 6, 8, 1); R(DARK, 4, 9, 8, 1);
      })
    };
  }
  function build(THREE, tint, k) {
    var ic = cache[k] || (cache[k] = icons(THREE, tint)), g = new THREE.Group();
    function M(tex) { return new THREE.MeshLambertMaterial({ map: tex }); }
    g.add(new THREE.Mesh(new THREE.BoxGeometry(0.8, 0.8, 0.8),
      [M(ic.right), M(ic.left), M(ic.top), M(ic.bottom), M(ic.back), M(ic.front)]));
    return g;
  }
  return {
    hash: hash,
    count: HUES.length,
    hues: HUES,
    variantOf: function (seed) { return (typeof seed === "number" ? Math.abs(seed) : hash(seed)) % HUES.length; },
    make: function (THREE, seed) {
      var k = this.variantOf(seed);
      var g = build(THREE, HUES[k], k);
      g.userData.variant = k;
      return g;
    }
  };
})();
'''


def viewer_data(design, sim):
    """Everything the 3D page needs: the shape, what gets placed, and the turtle's exact route."""
    code = {"t": 0, "d": 1, "m": 2, "p": 3}
    flat = []
    for e in sim.events:
        if e[0] == "t":
            flat.extend((0, e[1], 0, 0))
        else:
            flat.extend((code[e[0]],) + tuple(e[1:4]))
    sel = []
    for c in sorted(design.sel, key=lambda c: (c[1], c[2], c[0])):
        sel.extend(c)
    place = []
    targets = build_place(design)
    for c in sorted(targets, key=lambda c: (c[1], c[2], c[0])):
        place.extend((c[0], c[1], c[2], targets[c]))
    cc = design.chest_cell if design.chest else None
    return {
        "name": design.name, "w": design.w, "d": design.d, "h": design.h,
        "turtle": list(design.turtle), "chest": list(cc) if cc else None,
        "sel": sel, "place": place,
        "inv": {str(s): n for s, n in design.inv.items()},
        "colors": {str(s): display_color(n) for s, n in design.inv.items()},
        "tiles": {str(s): tile_hex(n) for s, n in design.inv.items() if tile_hex(n)},
        "digTile": tile_hex("minecraft:stone"),
        "pattern": dict(PATTERNS).get(design.pattern, design.pattern),
        "torches": dict(TORCH_MODES).get(design.torch_mode, design.torch_mode),
        "events": flat, "moves": sim.moves, "seconds": round(sim.seconds, 1),
        "skin": design.skin, "skinBody": design.skin_body, "skinAccent": design.skin_accent,
        "version": VERSION,
    }


def build_viewer_html(design, sim, share=None, external_three=False):
    """One self-contained .html file (three.js included) that replays the turtle in 3D.
    With `share` the page also gets the links of a hosted page; with external_three it loads
    three.min.js from next to itself (so many hosted pages can share one copy)."""
    import gzip
    import html
    three = gzip.decompress(base64.b64decode("".join(THREE_JS_GZ))).decode("utf-8")
    vd = viewer_data(design, sim)
    if share:
        vd["share"] = share
    data = json.dumps(vd, separators=(",", ":")).replace("<", "\\u003c")
    page = VIEWER_TEMPLATE.replace("@@TITLE@@", html.escape(design.name))
    if external_three:
        page = page.replace("<script>@@THREE@@</script>", '<script src="three.min.js"></script>')
    # the big pieces go in last, so nothing inside them is ever mistaken for a marker
    return page.replace("@@THREE@@", script_safe(three)).replace("@@TURTLE3D@@", script_safe(TURTLE3D_JS)).replace("@@DATA@@", script_safe(data))


def three_source():
    import gzip
    return gzip.decompress(base64.b64decode("".join(THREE_JS_GZ))).decode("utf-8")


def script_safe(text):
    return text.replace("</script", "<\\/script")
# Estimates (fuel, items, chests, time) shown before you upload a design.
# ---------------------------------------------------------------------------- estimates before you upload
COAL_FUEL = 80            # one coal / charcoal drives a turtle 80 blocks
STACK = 64
CHEST_SLOTS = 27          # one single chest


def _pretty(item):
    return (item or "?").split(":", 1)[-1].replace("_", " ")


def estimate(design, sim=None):
    """What the job will cost, worked out from the exact route. Returns a dict with plain numbers,
    `lines` (what to show) and `warnings` (things that will stop or slow the turtle)."""
    sim = sim or simulate(design)
    run, total, skipped = build_run(design)
    needs = supply_needs(design)
    fuel = int(sim.moves * 1.1) + 20                  # a little extra for trips home to unload
    coal = -(-fuel // COAL_FUEL)
    secs = sim.seconds
    dug_stacks = -(-sim.digs // STACK)
    lines, warns = [], []
    lines.append("Route: %d moves, %d digs, %d blocks placed." % (sim.moves, sim.digs, sim.places))
    lines.append("Time: about %s in the game (fast on a server with a quick tick rate)." % fmt_duration(secs))
    lines.append("Fuel: about %d (%d coal or %d charcoal)." % (fuel, coal, coal))
    if design.chest:
        lines.append("It digs up about %d blocks (%d+ stacks) and carries them to the chest." % (sim.digs, dug_stacks))
    else:
        lines.append("It digs up about %d blocks (%d+ stacks) and needs you to empty it." % (sim.digs, dug_stacks))
    slots = []
    for slot in sorted(needs):
        item = design.inv.get(slot, "")
        n = needs[slot]
        stacks = -(-n // STACK)
        slots.append((slot, item, n, stacks))
        lines.append("Slot %d: %d x %s  (%d stack%s)" % (slot, n, _pretty(item), stacks, "" if stacks == 1 else "s"))
        if stacks > 1:
            warns.append("%s: needs %d, a slot holds 64. The turtle pauses and asks for more %d time%s - or use the same "
                         "block in more slots." % (_pretty(item).capitalize(), n, stacks - 1, "" if stacks == 2 else "s"))
    if design.chest and dug_stacks > CHEST_SLOTS:
        warns.append("The chest behind the turtle holds %d stacks; this job digs up at least %d. Use a double chest or a "
                     "barrel, or empty it while it works." % (CHEST_SLOTS, dug_stacks))
    if fuel > 20000:
        warns.append("It needs more fuel than a turtle holds (20000). Keep coal in the chest behind it; it fetches it."
                     if design.chest else
                     "It needs more fuel than a turtle holds (20000). Top it up by hand part way.")
    if skipped:
        warns.append("%d selected cells aren't connected to the start and will be skipped." % skipped)
    if len(design.inv) and not any(needs.values()):
        warns.append("Blocks are loaded in the turtle's slots but none are used.")
    return {"moves": sim.moves, "digs": sim.digs, "places": sim.places, "fuel": fuel, "coal": coal, "seconds": secs,
            "dug_stacks": dug_stacks, "slots": slots, "lines": lines, "warnings": warns}


def fmt_duration(seconds):
    seconds = int(seconds)
    if seconds < 90:
        return "%d seconds" % seconds
    if seconds < 5400:
        return "%d minutes" % round(seconds / 60.0)
    return "%.1f hours" % (seconds / 3600.0)


def estimate_text(est):
    out = "\n".join(est["lines"])
    if est["warnings"]:
        out += "\n\nHeads up:\n" + "\n".join("- " + w for w in est["warnings"])
    return out
# Fleet: the app's picture of every turtle (status, position, inventory, orders) and the web page served at /fleet.
# Versions: inventory + crafting queue per turtle (7.x), duplicate names are numbered (7.8), jobs of a Foreman are placed by offset from the
# Foreman itself - _foreman_site (8.1), every turtle reports its inventory and 'crafty' flag (8.0).
# =================================================================== fleet (many turtles at once)
FLEET_HTML = r'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Carve Fleet</title>
<style>
:root{--bg:#f4f1ea;--card:#fffdf8;--ink:#23201a;--mute:#756f62;--line:#ddd6c6;--ok:#2f8f4e;--warn:#c9831a;--bad:#c0392b;--off:#8d8778;--done:#3b6fb6;--accent:#d9792b}
@media (prefers-color-scheme:dark){:root{--bg:#1d1b17;--card:#27241f;--ink:#eee8da;--mute:#a39c8b;--line:#3b362d;--ok:#5cc47a;--warn:#e8a53a;--bad:#ef6c5b;--off:#8d8778;--done:#6fa0e0;--accent:#f0913f}}
*{box-sizing:border-box}[hidden]{display:none!important}body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.4 system-ui,sans-serif}
header{padding:16px 16px 4px;display:flex;align-items:baseline;gap:12px;flex-wrap:wrap}
h1{margin:0;font-size:20px}#sum{color:var(--mute);font-size:14px}
main{display:grid;grid-template-columns:repeat(auto-fill,minmax(290px,1fr));gap:12px;padding:12px 16px 24px}
.card{background:var(--card);border:1px solid var(--line);border-left:6px solid var(--off);border-radius:10px;padding:12px}
.card.idle{border-left-color:var(--done)}.card.working{border-left-color:var(--ok)}.card.attention{border-left-color:var(--warn)}.card.error{border-left-color:var(--bad)}
.card.finished,.card.stopped{border-left-color:var(--done)}.card.offline{border-left-color:var(--off);opacity:.75}
.top{display:flex;justify-content:space-between;gap:8px;align-items:baseline}
.nm{font-weight:650;font-size:16px;overflow-wrap:anywhere}.id{color:var(--mute);font-size:12px;white-space:nowrap}
.st{display:inline-block;margin:6px 0;padding:1px 8px;border-radius:99px;font-size:12px;font-weight:600;border:1px solid currentColor}
.working .st,.idle .st{color:var(--ok)}.attention .st{color:var(--warn)}.error .st{color:var(--bad)}.finished .st,.stopped .st{color:var(--done)}.offline .st,.stopping .st{color:var(--off)}
.bar{height:8px;background:var(--line);border-radius:4px;overflow:hidden;margin:4px 0}.bar i{display:block;height:100%;background:var(--accent)}
.msg{margin:6px 0;overflow-wrap:anywhere}.meta{color:var(--mute);font-size:13px;display:flex;flex-wrap:wrap;gap:4px 14px}
.btns{margin-top:8px;display:flex;gap:6px}button{font:inherit;padding:4px 10px;border:1px solid var(--line);background:transparent;color:var(--ink);border-radius:6px;cursor:pointer}
button:hover{border-color:var(--accent)}button:focus-visible{outline:2px solid var(--accent)}
nav{display:flex;gap:6px;padding:4px 16px}nav button.on{background:var(--accent);color:#fff;border-color:var(--accent)}
#mapbox{display:none;padding:8px 16px 24px}#mapbox.on{display:block}
.mapbar{display:flex;flex-wrap:wrap;gap:8px 14px;align-items:center;margin-bottom:8px;color:var(--mute);font-size:13px}
.mapbar input[type=number]{width:70px;font:inherit;padding:2px 4px;background:var(--card);color:var(--ink);border:1px solid var(--line);border-radius:4px}
.act{color:var(--accent);font-style:italic}
#box3{display:none;padding:8px 16px 24px}#box3.on{display:block}
#cv3{width:100%;height:min(74vh,720px);background:#0e1016;border:1px solid var(--line);border-radius:8px;touch-action:none;cursor:grab;display:block}
#info3{margin-top:6px;min-height:2.6em;font-size:14px}#info3 b{font-weight:650}
canvas{width:100%;height:min(70vh,640px);background:#14130f;border:1px solid var(--line);border-radius:8px;touch-action:none;cursor:grab}
#tip{color:var(--mute);font-size:13px;margin-top:6px;min-height:1.4em}
.world{color:var(--ink)}
#stobox{display:none;padding:8px 16px 24px;max-width:900px}#stobox.on{display:block}
.krow{display:flex;flex-wrap:wrap;gap:6px 18px;color:var(--mute);font-size:13px;margin:4px 0 10px}
#find{font:inherit;padding:5px 8px;width:min(100%,360px);background:var(--card);color:var(--ink);border:1px solid var(--line);border-radius:6px}
table{border-collapse:collapse;width:100%;margin-top:10px;background:var(--card);border:1px solid var(--line);border-radius:8px}
th,td{padding:6px 10px;text-align:left;border-bottom:1px solid var(--line)}td.n,th.n{text-align:right;font-variant-numeric:tabular-nums}
td input[type=number]{width:72px;font:inherit;padding:2px 4px;background:var(--bg);color:var(--ink);border:1px solid var(--line);border-radius:4px}
#sto-msg{min-height:1.4em;margin-top:8px;color:var(--mute)}
#empty{color:var(--mute);padding:8px 16px;max-width:640px}
#fobox{display:none;padding:8px 16px 24px}#fobox.on{display:block}
.fsplit{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:14px}
@media (max-width:760px){.fsplit{grid-template-columns:1fr}}
.panel{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:12px}
.panel h2{margin:0 0 8px;font-size:15px;display:flex;justify-content:space-between;gap:8px;align-items:baseline}
.panel h2 span{color:var(--mute);font-size:12px;font-weight:400}
.slots{display:grid;grid-template-columns:repeat(4,1fr);gap:5px;max-width:340px}
.slot.cg{border-color:#6d8fc4;box-shadow:inset 0 0 0 1px rgba(109,143,196,.35)}.slot.res{border-color:#d9a928;background-color:#5a4410;box-shadow:inset 0 0 14px rgba(255,200,60,.45)}.slot.res.full{background-color:#6b5112}
.slot.cg i,.slot.res i{opacity:.85}
.slot{aspect-ratio:1;border:1px solid var(--line);border-radius:7px;padding:4px;display:flex;flex-direction:column;justify-content:space-between;font-size:11px;line-height:1.15;overflow:hidden;background:var(--bg)}
.slot.full{color:#fff;text-shadow:0 1px 2px rgba(0,0,0,.55);border-color:transparent}
.slot.pic{background-color:#2b2f3a;background-repeat:no-repeat;background-position:50% 24%;background-size:40%;image-rendering:pixelated}
.slot.pic span{margin-top:auto}
.ico{display:inline-block;width:24px;height:24px;vertical-align:middle;margin-right:8px;border-radius:4px;background-size:contain;background-repeat:no-repeat;background-position:center;image-rendering:pixelated}
.slot b{font-size:16px;align-self:flex-end;font-variant-numeric:tabular-nums}.slot i{font-style:normal;opacity:.6;font-size:11px}
.qrow{display:flex;gap:10px;align-items:center;padding:7px 4px;border-bottom:1px solid var(--line)}.qrow:last-child{border-bottom:0}
.qdot{width:10px;height:10px;border-radius:50%;flex:none;background:var(--off)}
.qrow.now .qdot{background:var(--ok);box-shadow:0 0 0 3px color-mix(in srgb,var(--ok) 30%,transparent)}.qrow.wait .qdot{background:var(--warn)}.qrow.done .qdot{background:var(--done)}
.qrow.done{color:var(--mute)}.qrow.now{font-weight:650}.qtag{margin-left:auto;font-size:12px;color:var(--mute)}
#fosel{font:inherit;padding:3px 6px;background:var(--card);color:var(--ink);border:1px solid var(--line);border-radius:6px}
</style></head><body>
<header><h1>Carve Fleet</h1><span id="sum">connecting...</span></header>
<div id="empty" hidden>No turtle has reported yet. Start a program that was uploaded with live reporting on, and make sure the turtle may reach this address.</div>
<nav><button id="tabF" class="on">Turtles</button><button id="tabM">Map</button><button id="tab3">3D map</button><button id="tabS">Storage</button><button id="tabO">Inventory</button></nav>
<main id="grid"></main>
<section id="mapbox">
<div class="mapbar">
<label>View <select id="mode"><option value="top">from above</option><option value="slice">one layer</option></select></label>
<label id="ylab" hidden>Layer y <input id="ylay" type="number" value="64"></label>
<button id="home">Centre on turtles</button><span id="mcount"></span>
</div>
<canvas id="cv"></canvas>
<div id="tip">Drag to move, scroll or pinch to zoom. Scouts fill the map in; every turtle with a known start position is a dot.</div>
</section>
<section id="box3">
<div class="mapbar">
<label>Distance <select id="r3"><option value="24">24 blocks</option><option value="40" selected>40 blocks</option><option value="64">64 blocks</option><option value="96">96 blocks</option></select></label>
<label>Follow <select id="f3"><option value="">nobody</option></select></label>
<button id="home3">Centre on turtles</button><span id="c3"></span>
</div>
<canvas id="cv3"></canvas>
<div id="info3">Drag to turn, right-drag or shift-drag to move, scroll or pinch to zoom, click a turtle for details.</div>
</section>
<section id="fobox">
<div class="mapbar"><span id="fotitle">The Foreman has not reported yet.</span><select id="fosel" hidden aria-label="Which turtle"></select></div>
<div class="fsplit">
<div class="panel"><h2>Inventory <span id="fonum"></span></h2><div class="slots" id="fogrid"></div></div>
<div class="panel"><h2>Crafting queue <span id="fonq"></span></h2><div id="foq"></div></div>
</div>
</section>
<section id="stobox">
<div id="keepers" class="krow">No storage keeper has reported yet. Start a Storage keeper job with live reporting on.</div>
<input id="find" type="search" placeholder="Search items, e.g. iron" aria-label="Search items">
<table><thead><tr><th>Item</th><th class="n">In storage</th><th class="n">Stacks</th><th>Get some</th></tr></thead><tbody id="items"></tbody></table>
<div id="sto-msg" role="status"></div>
</section>
<script>
"use strict";
const grid=document.getElementById("grid"),sum=document.getElementById("sum"),empty=document.getElementById("empty");
const LABEL={idle:"Idle, ready for a job",working:"Working",attention:"Needs attention",error:"Error",finished:"Finished",stopped:"Stopped",offline:"Offline",stopping:"Stopping..."};
function el(tag,cls,text){const e=document.createElement(tag);if(cls)e.className=cls;if(text!==undefined)e.textContent=text;return e}
function ago(s){if(s<5)return"just now";if(s<90)return Math.round(s)+" s ago";if(s<5400)return Math.round(s/60)+" min ago";return Math.round(s/3600)+" h ago"}
let rows=[];
const ICON={};                                   // item id -> picture (data URL) or false (no texture: solid colour)
let iconBusy=false;
function hexUrl(h){const c=document.createElement("canvas");c.width=c.height=16;const x=c.getContext("2d"),im=x.createImageData(16,16);
  for(let i=0;i<256;i++){const p=h.substr(i*6,6);if(p[0]==="-")continue;im.data[i*4]=parseInt(p.substr(0,2),16);im.data[i*4+1]=parseInt(p.substr(2,2),16);im.data[i*4+2]=parseInt(p.substr(4,2),16);im.data[i*4+3]=255}
  x.putImageData(im,0,0);return c.toDataURL()}
function wantIcons(names,again){
  const need=[...new Set(names)].filter(n=>n&&!(n in ICON));
  if(!need.length||iconBusy)return;iconBusy=true;need.forEach(n=>ICON[n]=false);
  fetch("/icons?names="+encodeURIComponent(need.join(",")),{cache:"no-store"}).then(r=>r.json()).then(d=>{for(const n of need)if(d[n])ICON[n]=hexUrl(d[n])}).catch(()=>{}).finally(()=>{iconBusy=false;again()})}
function renderForeman(){
  if(!fobox.classList.contains("on"))return;
  const who=rows.filter(t=>t.inv),sel=document.getElementById("fosel");
  if(!who.length){fotitle.textContent="No turtle has reported its inventory yet. Start one and keep live reporting on.";fogrid.replaceChildren();foq.replaceChildren();fonum.textContent=fonq.textContent="";sel.hidden=true;return}
  if(who.length>1){sel.hidden=false;if(sel.options.length!==who.length)sel.replaceChildren(...who.map(t=>{const o=el("option","",t.label||t.name||("#"+t.id));o.value=t.id;return o}))}else sel.hidden=true;
  if(invWanted!==null&&who.some(x=>x.id===invWanted)){sel.value=String(invWanted);invWanted=null}
  const t=who.find(x=>String(x.id)===sel.value)||who[0];
  fotitle.textContent=(t.label||t.name||("Turtle "+t.id))+" - "+(t.act||t.msg||"");
  const by={};for(const [s,n,c] of t.inv)by[s]=[n,c];
  const tiles=[];let used=0;
  const CG=[1,2,3,5,6,7,9,10,11];
  for(let s=1;s<=16;s++){const e=by[s],d=el("div","slot"+(e?" full":"")+(t.crafty&&CG.includes(s)?" cg":"")+(t.crafty&&s===16?" res":""));
    if(e){used++;const pic=ICON[e[0]];
      if(pic){d.classList.add("pic");d.style.backgroundImage="url("+pic+")"}else d.style.background=colour(e[0]);
      d.append(el("i","","slot "+s),el("span","",pretty(e[0])),el("b","",String(e[1])))}
    else d.append(el("i","",t.crafty&&s===16?"result":"slot "+s));
    tiles.push(d)}
  fogrid.replaceChildren(...tiles);fonum.textContent=used+" of 16 slots in use"+(t.crafty?" · blue = crafting grid, gold = result":"");invName=t.label||t.name||("Turtle "+t.id);
  wantIcons(t.inv.map(e=>e[1]),renderForeman);
  const q=t.q||[],TAGS={now:"now",wait:"waiting",todo:"queued",done:"done"};
  foq.replaceChildren(...(q.length?q.map(e=>{const r=el("div","qrow "+e.s);r.append(el("span","qdot"),el("span","",e.t),el("span","qtag",TAGS[e.s]));return r}):[el("div","meta","Nothing queued.")]));
  fonq.textContent=q.filter(e=>e.s!=="done").length+" open";
}
function post(path,body){return fetch(path,{method:"POST",body:JSON.stringify(body)}).then(load)}
function card(t){
  const c=el("div","card "+t.state);
  const top=el("div","top");
  top.append(el("span","nm",t.label||t.name||("Turtle "+t.id)),el("span","id","#"+t.id+" · "+t.kind));
  c.append(top,el("span","st",LABEL[t.state]||t.state));
  if(t.total>0){const b=el("div","bar"),i=el("i");i.style.width=Math.min(100,100*t.n/t.total)+"%";b.append(i);c.append(b,el("div","meta",t.n+" / "+t.total))}
  if(t.name&&t.label&&t.label!==t.name)c.append(el("div","meta",t.name));
  c.append(el("div","msg",t.msg||"-"));
  if(t.act)c.append(el("div","meta act","Trying to: "+t.act));
  const m=el("div","meta");
  m.append(el("span","","fuel "+t.fuel),el("span","",t.world?("world "+t.world.join(", ")):("start x"+t.x+" y"+t.y+" z"+t.z)),el("span","",ago(t.age)));
  c.append(m);
  const btns=el("div","btns");
  if(["working","attention","error"].includes(t.state)){
    const s=el("button","","Stop");s.title="Ends the program; carve resume continues it later";
    s.onclick=()=>{if(confirm("Stop "+(t.label||t.name||t.id)+"? It stops at its next report; 'carve resume' continues.")) post("/cmd",{id:t.id,cmd:"stop"})};btns.append(s)}
  const f=el("button","","Forget");f.onclick=()=>post("/forget",{id:t.id});btns.append(f);
  c.append(btns);return c}
async function load(){
  try{
    const d=await (await fetch("/fleet",{cache:"no-store"})).json();
    const ts=d.turtles;rows=ts;grid.replaceChildren(...ts.map(card));renderForeman();refreshInvTab();
    empty.hidden=ts.length>0||grid.hidden;
    const n=s=>ts.filter(t=>t.state===s).length;
    sum.textContent=ts.length+" turtle"+(ts.length===1?"":"s")+" · "+n("working")+" working · "+n("attention")+" need attention · "+n("offline")+" offline";
  }catch(e){sum.textContent="Lost contact with the Designer."}
}

/* ---------- 3D map (three.js, loaded the first time this tab opens) ---------- */
let g3=null,g3loading=false;
function loadScript(u){return new Promise((ok,bad)=>{const s=document.createElement("script");s.src=u;s.onload=ok;s.onerror=()=>bad(new Error(u));document.head.append(s)})}
async function start3d(){
  if(g3){g3.on=true;g3.refresh();return}
  if(g3loading)return;g3loading=true;
  const info=document.getElementById("info3");
  try{await loadScript("/three.min.js");await loadScript("/turtle3d.js")}catch(e){info.textContent="Could not load the 3D library from the Designer ("+e.message+").";g3loading=false;return}
  const cv3=document.getElementById("cv3"),r3=document.getElementById("r3"),f3=document.getElementById("f3"),home3=document.getElementById("home3"),c3=document.getElementById("c3");
  const renderer=new THREE.WebGLRenderer({canvas:cv3,antialias:true});
  const scene=new THREE.Scene();scene.background=new THREE.Color(0x0e1016);scene.fog=new THREE.Fog(0x0e1016,60,220);
  scene.add(new THREE.AmbientLight(0xffffff,0.62));const sun=new THREE.DirectionalLight(0xffffff,0.75);sun.position.set(30,80,20);scene.add(sun);
  const camera=new THREE.PerspectiveCamera(55,1,0.1,600);
  const tgt=new THREE.Vector3(0,64,0);let theta=0.6,phi=1.0,radius=40;
  const cube=new THREE.BoxGeometry(1,1,1),blockMat=new THREE.MeshLambertMaterial({color:0xffffff});
  let blocks=null,loadedAt=null,busy3=false,turtles=[],models=new Map(),picked=null,centered=false;
  const worldGroup=new THREE.Group();scene.add(worldGroup);
  const col=new THREE.Color();
  function fit(){const r=cv3.getBoundingClientRect(),d=Math.min(window.devicePixelRatio||1,2);renderer.setPixelRatio(d);renderer.setSize(r.width,r.height,false);camera.aspect=r.width/Math.max(1,r.height);camera.updateProjectionMatrix()}
  addEventListener("resize",fit);fit();
  function place(){camera.position.set(tgt.x+radius*Math.sin(phi)*Math.sin(theta),tgt.y+radius*Math.cos(phi),tgt.z+radius*Math.sin(phi)*Math.cos(theta));camera.lookAt(tgt)}
  const ROT={north:0,east:-Math.PI/2,south:Math.PI,west:Math.PI/2};
  function label(t){
    const txt=(t.label||t.name||("#"+t.id)),a=(t.act||t.msg||"").slice(0,46);
    const c=document.createElement("canvas");c.width=512;c.height=96;const x=c.getContext("2d");
    x.fillStyle="rgba(10,12,18,.78)";x.beginPath();x.roundRect?x.roundRect(4,4,504,88,14):x.rect(4,4,504,88);x.fill();
    x.font="bold 34px system-ui";x.fillStyle="#fff";x.textBaseline="top";x.fillText(txt,18,10);
    x.font="26px system-ui";x.fillStyle="#f0b36a";x.fillText(a,18,54);
    const tex=new THREE.CanvasTexture(c);const sp=new THREE.Sprite(new THREE.SpriteMaterial({map:tex,depthTest:false,transparent:true}));
    sp.scale.set(6.4,1.2,1);sp.renderOrder=10;return sp}
  function syncTurtles(){
    const seen=new Set();
    for(const t of turtles){
      seen.add(t.id);let m=models.get(t.id);
      if(!m){const g=new THREE.Group(),body=CarveTurtle.make(THREE,t.id);body.scale.setScalar(0.96);g.add(body);g.userData={id:t.id,body};scene.add(g);m={g,sig:"",sp:null};models.set(t.id,m)}
      m.g.position.set(t.world[0]+.5,t.world[1]+.5,t.world[2]+.5);m.g.userData.body.rotation.y=ROT[t.dir||t.facing]||0;
      const sig=(t.label||t.name)+"|"+(t.act||t.msg||"").slice(0,46);
      if(sig!==m.sig){if(m.sp){m.g.remove(m.sp);m.sp.material.map.dispose();m.sp.material.dispose()}m.sp=label(t);m.sp.position.set(0,1.5,0);m.g.add(m.sp);m.sig=sig}
      m.g.userData.row=t}
    for(const [id,m] of models)if(!seen.has(id)){scene.remove(m.g);models.delete(id)}
    const keep=f3.value;f3.replaceChildren(new Option("nobody",""),...turtles.map(t=>new Option(t.label||t.name||("#"+t.id),String(t.id))));f3.value=turtles.some(t=>String(t.id)===keep)?keep:"";
  }
  function build(d){
    if(blocks){worldGroup.remove(blocks);blocks.dispose()}
    const n=d.cells.length;blocks=new THREE.InstancedMesh(cube,blockMat,Math.max(1,n));
    const cols=d.names.map(nm=>new THREE.Color(colour(nm).startsWith("hsl")?hsl2hex(colour(nm)):colour(nm))),M=new THREE.Matrix4();
    for(let i=0;i<n;i++){const [x,y,z,k]=d.cells[i];M.makeTranslation(x+.5,y+.5,z+.5);blocks.setMatrixAt(i,M);col.copy(cols[k]||cols[0]);const j=((x*7+y*13+z*17)%5)*0.012;col.offsetHSL(0,0,j-0.024);blocks.setColorAt(i,col)}
    blocks.count=n;blocks.instanceMatrix.needsUpdate=true;if(blocks.instanceColor)blocks.instanceColor.needsUpdate=true;worldGroup.add(blocks);
  }
  function hsl2hex(s){const m=/hsl\((\d+),(\d+)%,(\d+)%\)/.exec(s);const c=new THREE.Color();c.setHSL(m[1]/360,m[2]/100,m[3]/100);return "#"+c.getHexString()}
  async function refresh(){
    if(busy3||!g3.on)return;busy3=true;
    try{
      const rad=+r3.value,u="/map3d?cx="+Math.round(tgt.x)+"&cy="+Math.round(tgt.y)+"&cz="+Math.round(tgt.z)+"&r="+rad+"&ry="+Math.round(rad*0.8);
      const d=await (await fetch(u,{cache:"no-store"})).json();
      turtles=d.turtles;
      if(!centered&&turtles.length){centered=true;centre();busy3=false;return refresh()}
      build(d);loadedAt=tgt.clone();syncTurtles();
      c3.textContent=d.count+" blocks known · showing "+d.cells.length+(d.truncated?" (nearest only)":"")+" · "+turtles.length+" turtle"+(turtles.length===1?"":"s")+" placed";
    }catch(e){c3.textContent="Lost contact with the Designer."}
    busy3=false}
  function centre(){if(!turtles.length)return;const a=turtles.reduce((s,t)=>[s[0]+t.world[0],s[1]+t.world[1],s[2]+t.world[2]],[0,0,0]);tgt.set(a[0]/turtles.length+.5,a[1]/turtles.length+.5,a[2]/turtles.length+.5);radius=18}
  home3.onclick=()=>{centre();refresh()};r3.onchange=refresh;
  // orbit / pan / zoom
  const ptrs={};cv3.addEventListener("contextmenu",e=>e.preventDefault());
  let moved=0;
  cv3.addEventListener("pointerdown",e=>{cv3.setPointerCapture(e.pointerId);ptrs[e.pointerId]={x:e.clientX,y:e.clientY,b:e.button,sh:e.shiftKey};moved=0});
  cv3.addEventListener("pointerup",e=>{const was=ptrs[e.pointerId];delete ptrs[e.pointerId];if(was&&moved<5&&was.b===0)pick(e)});
  cv3.addEventListener("pointercancel",e=>{delete ptrs[e.pointerId]});
  cv3.addEventListener("pointermove",e=>{const p=ptrs[e.pointerId];if(!p)return;const dx=e.clientX-p.x,dy=e.clientY-p.y,ids=Object.keys(ptrs);moved+=Math.abs(dx)+Math.abs(dy);
    if(ids.length>=2){const o=ptrs[ids[0]==e.pointerId?ids[1]:ids[0]],before=Math.hypot(p.x-o.x,p.y-o.y),after=Math.hypot(e.clientX-o.x,e.clientY-o.y);if(before>0)radius=Math.max(4,Math.min(300,radius*before/Math.max(after,1)));p.x=e.clientX;p.y=e.clientY;return}
    p.x=e.clientX;p.y=e.clientY;
    if(p.b===2||p.b===1||p.sh){const k=radius*0.0016,r=new THREE.Vector3(),u=new THREE.Vector3();camera.matrix.extractBasis(r,u,new THREE.Vector3());tgt.addScaledVector(r,-dx*k).addScaledVector(u,dy*k);f3.value=""}
    else{theta-=dx*0.008;phi=Math.max(0.08,Math.min(Math.PI-0.08,phi-dy*0.008))}});
  cv3.addEventListener("wheel",e=>{e.preventDefault();radius=Math.max(4,Math.min(300,radius*Math.exp(e.deltaY*0.001)))},{passive:false});
  const ray=new THREE.Raycaster(),mouse=new THREE.Vector2();
  function pick(e){const r=cv3.getBoundingClientRect();mouse.set((e.clientX-r.left)/r.width*2-1,-((e.clientY-r.top)/r.height)*2+1);ray.setFromCamera(mouse,camera);
    const hits=ray.intersectObjects([...models.values()].map(m=>m.g.userData.body),true);
    if(!hits.length){picked=null;info.textContent="Drag to turn, right-drag or shift-drag to move, scroll or pinch to zoom, click a turtle for details.";return}
    let o=hits[0].object;while(o&&!o.parent.userData.id)o=o.parent;picked=o&&o.parent?o.parent.userData.id:null;showInfo();if(picked!==null&&rows.some(x=>x.id===picked&&x.inv)){invWanted=picked;show("foreman")}}
  function showInfo(){const m=models.get(picked);if(!m)return;const t=m.g.userData.row;info.replaceChildren();
    const b=document.createElement("b");b.textContent=(t.label||t.name||("#"+t.id))+(t.name&&t.label&&t.name!==t.label?" ("+t.name+")":"");info.append(b," · "+(LABEL[t.state]||t.state)+" · fuel "+t.fuel+" · at "+t.world.join(", "));
    info.append(document.createElement("br"),"Doing: "+(t.msg||"-")+(t.act?"  |  Trying to: "+t.act:""))}
  g3={on:true,refresh};
  let last=0;
  function frame(ts){requestAnimationFrame(frame);if(!g3.on)return;
    const f=f3.value&&models.get(+f3.value);if(f)tgt.lerp(f.g.position,0.15);
    if(ts-last>3000){last=ts;refresh()}
    for(const m of models.values())if(m.sp){const d=camera.position.distanceTo(m.g.position),h=Math.max(0.8,d*0.04);m.sp.scale.set(h*5.33,h,1)}
    place();if(picked)showInfo();renderer.render(scene,camera)}
  requestAnimationFrame(frame);refresh();
}
load();setInterval(load,2000);
if(location.hash==="#map")setTimeout(()=>show("map"),0);
if(location.hash==="#3d")setTimeout(()=>show("3d"),0);
if(location.hash==="#storage")setTimeout(()=>show("store"),0);
if(location.hash==="#foreman")setTimeout(()=>show("foreman"),0);
/* ---------- map ---------- */
const cv=document.getElementById("cv"),cx=cv.getContext("2d"),tabF=document.getElementById("tabF"),tabM=document.getElementById("tabM"),box=document.getElementById("mapbox");
const modeSel=document.getElementById("mode"),ylab=document.getElementById("ylab"),ylay=document.getElementById("ylay"),mcount=document.getElementById("mcount");
let view={cx:0,cz:0,scale:8},data={names:[],cells:[],turtles:[]},fitted=false,busy=false;
const KNOWN={air:"#26231d",grass_block:"#4f9a3c",dirt:"#7a5632",stone:"#7d7d7d",cobblestone:"#6a6a6a",water:"#3563c9",lava:"#e5650f",sand:"#d8c98b",gravel:"#8c8680",
 oak_log:"#6b5130",oak_leaves:"#2f6a2a",spruce_log:"#4a3822",spruce_leaves:"#2a4a35",birch_log:"#d3cdb8",birch_leaves:"#58803f",snow:"#f2f6f8",snow_block:"#f2f6f8",ice:"#a8c8f0",
 bedrock:"#222",deepslate:"#4a4a52",netherrack:"#7a3030",sandstone:"#cdbb85",clay:"#9aa3b3",coal_ore:"#444",iron_ore:"#a58b78",chest:"#a07820",furnace:"#666",crafting_table:"#a0713a"};
function colour(n){n=String(n).replace(/^minecraft:/,"");if(KNOWN[n])return KNOWN[n];if(n==="unknown")return"#b0b";let h=0;for(const c of n)h=(h*31+c.charCodeAt(0))>>>0;return"hsl("+(h%360)+",38%,46%)"}
function size(){const r=cv.getBoundingClientRect(),d=window.devicePixelRatio||1;cv.width=Math.round(r.width*d);cv.height=Math.round(r.height*d);return d}
function span(){const r=cv.getBoundingClientRect();return{w:r.width/view.scale,h:r.height/view.scale}}
function toScreen(x,z){const r=cv.getBoundingClientRect();return[(x-view.cx)*view.scale+r.width/2,(z-view.cz)*view.scale+r.height/2]}
function draw(){
  const d=size();cx.setTransform(d,0,0,d,0,0);const r=cv.getBoundingClientRect();cx.clearRect(0,0,r.width,r.height);
  const sc=Math.max(1,view.scale),cols=data.names.map(colour);
  for(const [x,z,y,i] of data.cells){const [sx,sy]=toScreen(x-.5,z-.5);cx.fillStyle=cols[i]||"#b0b";cx.fillRect(sx,sy,sc+.5,sc+.5)}
  cx.font="12px system-ui";cx.textBaseline="middle";
  for(const t of data.turtles){const [sx,sy]=toScreen(t.world[0],t.world[2]);
    cx.beginPath();cx.arc(sx,sy,6,0,6.3);cx.fillStyle=t.state==="offline"?"#8d8778":t.state==="attention"||t.state==="error"?"#e8a53a":"#5cc47a";cx.fill();cx.strokeStyle="#000";cx.lineWidth=2;cx.stroke();
    const label=(t.label||t.name||("#"+t.id));cx.lineWidth=3;cx.strokeStyle="#000";cx.strokeText(label,sx+9,sy);cx.fillStyle="#fff";cx.fillText(label,sx+9,sy)}
}
async function loadMap(){
  if(busy||!box.classList.contains("on"))return;busy=true;
  try{const sp=span(),rad=Math.min(120,Math.ceil(Math.max(sp.w,sp.h)/2)+2),mode=modeSel.value;
    const u="/map?cx="+Math.round(view.cx)+"&cz="+Math.round(view.cz)+"&r="+rad+"&mode="+mode+"&y="+(+ylay.value||0);
    data=await (await fetch(u,{cache:"no-store"})).json();
    if(!fitted&&data.turtles.length){view.cx=data.turtles[0].world[0];view.cz=data.turtles[0].world[2];fitted=true;busy=false;loadMap();return}
    const wt=(data.waiting||[]).map(w=>w.name+" ("+w.count+" blocks)").join(", ");
    mcount.textContent=data.count+" blocks known · "+data.turtles.length+" turtle"+(data.turtles.length===1?"":"s")+" placed"+(wt?" · WAITING for a start position: "+wt+" (set it in the Designer: Colony tab or Fleet > Set start position)":"");
    draw();
  }catch(e){mcount.textContent="Lost contact with the Designer."}
  busy=false}
let invWanted=null,invName="";
function refreshInvTab(){if(!fobox.classList.contains("on")){const t=rows.find(x=>x.inv);invName=t?(t.label||t.name||("Turtle "+t.id)):""}setInvTab()}
function setInvTab(){tabO.textContent=invName?"Inventory - "+invName:"Inventory"}
function show(v){v=v===true?"map":v===false?"fleet":v;const map=v==="map",sto=v==="store",d3=v==="3d",fo=v==="foreman";
  tabO.classList.toggle("on",fo);fobox.classList.toggle("on",fo);if(fo)renderForeman();setInvTab();
  tabF.classList.toggle("on",v==="fleet");tabM.classList.toggle("on",map);tabS.classList.toggle("on",sto);tab3.classList.toggle("on",d3);
  box.classList.toggle("on",map);stobox.classList.toggle("on",sto);box3.classList.toggle("on",d3);grid.hidden=v!=="fleet";if(v!=="fleet")empty.hidden=true;if(map){loadMap()}if(sto){loadStore()}if(g3)g3.on=d3;if(d3){start3d()}}
const tab3=document.getElementById("tab3"),box3=document.getElementById("box3");
const tabO=document.getElementById("tabO"),fobox=document.getElementById("fobox"),fotitle=document.getElementById("fotitle"),fogrid=document.getElementById("fogrid"),foq=document.getElementById("foq"),fonum=document.getElementById("fonum"),fonq=document.getElementById("fonq");
const tabS=document.getElementById("tabS"),stobox=document.getElementById("stobox");
tabF.onclick=()=>show("fleet");tabO.onclick=()=>show("foreman");document.getElementById("fosel").onchange=renderForeman;tabM.onclick=()=>show("map");tabS.onclick=()=>show("store");tab3.onclick=()=>show("3d");
/* ---------- storage ---------- */
const find=document.getElementById("find"),itemsEl=document.getElementById("items"),keepersEl=document.getElementById("keepers"),stoMsg=document.getElementById("sto-msg");
let store={keepers:[],items:[]},typing=false;
function pretty(n){return n.replace(/^minecraft:/,"").replace(/_/g," ")}
function renderStore(){
  wantIcons(store.items.map(e=>e.item),renderStore);
  keepersEl.replaceChildren(...(store.keepers.length?store.keepers.map(k=>el("span","",(k.name||"Keeper")+" #"+k.id+": "+k.chests+"/"+k.max+" chests, "+k.stacks+"/"+k.slots+" slots used"+(k.waiting?", "+k.waiting+" order"+(k.waiting===1?"":"s")+" waiting":"")+(k.age>90?" (not heard from for "+ago(k.age)+")":"")+(k.spare?"":" - no spare chests"))):[el("span","","No storage keeper has reported yet. Start a Storage keeper job with live reporting on.")]));
  const q=find.value.trim().toLowerCase(),rows=store.items.filter(e=>!q||e.item.toLowerCase().includes(q)||pretty(e.item).includes(q));
  itemsEl.replaceChildren(...rows.map(e=>{
    const tr=el("tr"),inp=el("input"),b=el("button","","Send to pickup chest");
    inp.type="number";inp.min=1;inp.max=Math.min(4096,e.count);inp.value=Math.min(64,e.count);inp.setAttribute("aria-label","How many "+pretty(e.item));
    b.onclick=()=>order(e,+inp.value);
    const td=el("td");td.append(inp," ",b);
    const nm=el("td"),ic=el("span","ico");
    if(ICON[e.item])ic.style.backgroundImage="url("+ICON[e.item]+")";else ic.style.background=colour(e.item);
    nm.append(ic,pretty(e.item));
    tr.append(nm,el("td","n",String(e.count)),el("td","n",String(Math.ceil(e.count/64))),td);return tr}));
}
async function loadStore(){
  if(!stobox.classList.contains("on")||typing||itemsEl.contains(document.activeElement))return;
  try{store=await (await fetch("/storage",{cache:"no-store"})).json();renderStore()}catch(e){stoMsg.textContent="Lost contact with the Designer."}}
async function order(e,count){
  if(!(count>=1)){stoMsg.textContent="Type how many you want.";return}
  const r=await fetch("/order",{method:"POST",body:JSON.stringify({item:e.item,count:count})}),t=await r.text();
  stoMsg.textContent=r.ok?("Asked for "+count+" "+pretty(e.item)+". The keeper brings them to its pickup chest at its next check."):("Not sent: "+t);loadStore()}
find.oninput=renderStore;find.onfocus=()=>{typing=true};find.onblur=()=>{typing=false};
setInterval(loadStore,3000);
modeSel.onchange=()=>{ylab.hidden=modeSel.value!=="slice";loadMap()};ylay.onchange=loadMap;
document.getElementById("home").onclick=()=>{if(data.turtles.length){view.cx=data.turtles[0].world[0];view.cz=data.turtles[0].world[2];loadMap()}};
let drag=null;const pts=new Map();let pinch=0;
cv.onpointerdown=e=>{cv.setPointerCapture(e.pointerId);pts.set(e.pointerId,[e.clientX,e.clientY]);drag=[e.clientX,e.clientY,view.cx,view.cz];cv.style.cursor="grabbing"};
cv.onpointermove=e=>{
  if(!pts.has(e.pointerId))return;pts.set(e.pointerId,[e.clientX,e.clientY]);
  if(pts.size===2){const [a,b]=[...pts.values()],dd=Math.hypot(a[0]-b[0],a[1]-b[1]);if(pinch){view.scale=Math.max(1,Math.min(60,view.scale*dd/pinch));draw()}pinch=dd;return}
  if(drag){view.cx=drag[2]-(e.clientX-drag[0])/view.scale;view.cz=drag[3]-(e.clientY-drag[1])/view.scale;draw()}};
cv.onpointerup=cv.onpointercancel=e=>{pts.delete(e.pointerId);pinch=0;drag=null;cv.style.cursor="grab";loadMap()};
cv.onwheel=e=>{e.preventDefault();view.scale=Math.max(1,Math.min(60,view.scale*(e.deltaY<0?1.2:1/1.2)));draw();loadMap()};
cv.onmousemove=e=>{const r=cv.getBoundingClientRect(),x=Math.round((e.clientX-r.left-r.width/2)/view.scale+view.cx),z=Math.round((e.clientY-r.top-r.height/2)/view.scale+view.cz);
  const c=data.cells.find(c=>c[0]===x&&c[1]===z);document.getElementById("tip").textContent="x "+x+"  z "+z+(c?"  y "+c[2]+"  "+data.names[c[3]]:"  (unknown)")};
setInterval(loadMap,3000);addEventListener("resize",draw);
</script></body></html>
'''

_ATTENTION = re.compile(r"out of fuel|blocked|inventory full|empty me|put |can't|cannot|could not|did not|won't|"
                        r"waiting for|nothing to|stuck|too full", re.I)


def _clip(v, n=200):
    return str(v if v is not None else "")[:n]


def _num(v, default=0):
    try:
        return int(v)
    except (TypeError, ValueError):
        return default


# where each kind of job keeps its chests, as (right, up, forward) from its start cell
STATION_CHESTS = {
    "treefarm": {"out": (0, 0, -1)},
    "miner": {"out": (0, 0, -1)},
    "smelter": {"in": (0, 0, -1), "out": (-1, 0, 0)},
    "crafter": {"in": (0, 0, -1), "out": (-1, 0, 0)},
    "keeper": {"in": (0, 0, -1), "out": (-1, 0, 0)},
}

NAME_LIST = ["Abrams", "Bebop", "Dynamo", "Grey Talon", "Haze", "Infernus", "Ivy", "Kelvin", "Lady Geist", "Lash", "McGinnis", "Krill", "Paradox", "Pocket", "Seven", "Shiv", "Vindicta", "Viscous", "Warden", "Wraith", "Yamato", "Calico", "Holliday", "Vyper", "Sinclair", "Mirage", "Drifter", "Victor", "Paige", "Billy", "Rem", "Mo"]
NAME_ORDER = random.sample(NAME_LIST, len(NAME_LIST))      # one fresh shuffle per run: the first turtle is not always called the same


FACINGS = {"north": (0, -1), "east": (1, 0), "south": (0, 1), "west": (-1, 0)}


def local_to_world(anchor, rel):
    """anchor = (x, y, z, facing) is where a turtle's start cell is in the world and which way it faced;
    rel = (right, up, forward) measured from that start cell. Returns the world (x, y, z)."""
    ax, ay, az, face = anchor
    fx, fz = FACINGS[face]
    rx, rz = -fz, fx                       # "right" of the facing direction
    return (ax + rel[0] * rx + rel[2] * fx, ay + rel[1], az + rel[0] * rz + rel[2] * fz)


def world_to_local(anchor, w):
    """The opposite of local_to_world: (right, up, forward) of world point w, seen from the start cell."""
    ax, ay, az, face = anchor
    fx, fz = FACINGS[face]
    rx, rz = -fz, fx
    dx, dz = w[0] - ax, w[2] - az
    return (dx * rx + dz * rz, w[1] - ay, dx * fx + dz * fz)


def facing_code(agent_face, target_face):
    """A turtle's direction number (1 forward, 2 right, 3 back, 4 left) for facing target_face in the world,
    when its own start faced agent_face."""
    tx, tz = FACINGS[target_face]
    fx, fz = FACINGS[agent_face]
    rx, rz = -fz, fx
    lz, lx = tx * fx + tz * fz, tx * rx + tz * rz
    return {(0, 1): 1, (1, 0): 2, (0, -1): 3, (-1, 0): 4}[(lx, lz)]


def design_footprint(d):
    """Where a dig design lives, in (right, up, forward) from the start cell: [x0, y0, z0, x1, y1, z1]."""
    return [1 - d.tx, 1 - d.ty, 1 - d.tz, d.w - d.tx, d.h - d.ty, d.d - d.tz]


def auto_footprint(job):
    """The space an automation job uses (trees included), or None when it builds nothing (scout, agent)."""
    k = job["kind"]
    if k == "treefarm":
        s = job["spacing"]
        return [-3, -1, -2, s * job["cols"] + 2, 9, s * job["rows"] + 2]
    if k == "smelter":
        return [-2, -1, -2, job["furnaces"] + 1, 2, 4]
    if k == "crafter":
        return [-2, -1, -2, 2, 2, 2]
    if k == "keeper":
        return [-2, -1, -2, 2, 2, job["length"] + 1]
    if k == "miner":
        return [-1, -job["depth"] - 1, -job["rib"] - 1, job["reach"] + 1, 1, job["rib"] + 1]
    return None


def world_box(anchor, foot):
    """The world-space box (x0, y0, z0, x1, y1, z1) covered by a local footprint."""
    pts = [local_to_world(anchor, (x, y, z)) for x in (foot[0], foot[3]) for y in (foot[1], foot[4]) for z in (foot[2], foot[5])]
    return tuple(min(p[i] for p in pts) for i in range(3)) + tuple(max(p[i] for p in pts) for i in range(3))


def boxes_overlap(a, b):
    return all(a[i] <= b[i + 3] and b[i] <= a[i + 3] for i in range(3))


def _solve_facing(rel0, g0, rel1, g1):
    """Which way did the start face, judging from two GPS fixes at two places the turtle had been?"""
    dl = (rel1[0] - rel0[0], rel1[2] - rel0[2])
    dg = (g1[0] - g0[0], g1[2] - g0[2])
    if dl == (0, 0):
        return None
    for face in FACINGS:
        w = local_to_world((0, 0, 0, face), (dl[0], 0, dl[1]))
        if (w[0], w[2]) == dg:
            return face
    return None


def _block_name(v):
    v = str(v)[:48].replace("minecraft:", "")
    return v if re.fullmatch(r"[a-z0-9_:./\-]+", v) else "unknown"


class WorldMap:
    """Every block any scout has reported, in world coordinates."""
    MAX_CELLS = 600000

    def __init__(self):
        self.lock = threading.Lock()
        self.cols = {}                     # (x, z) -> {y: name index}
        self.names, self.index = [], {}
        self.count = 0

    def add(self, x, y, z, name):
        with self.lock:
            i = self.index.get(name)
            if i is None:
                i = self.index[name] = len(self.names)
                self.names.append(name)
            col = self.cols.setdefault((x, z), {})
            if y not in col:
                if self.count >= self.MAX_CELLS:
                    return False
                self.count += 1
            col[y] = i
            return True

    def view(self, cx, cz, r, mode="top", y=0):
        """Cells in a square around (cx, cz): the highest solid block of every column (top), or one layer (slice)."""
        out = []
        with self.lock:
            for x in range(cx - r, cx + r + 1):
                for z in range(cz - r, cz + r + 1):
                    col = self.cols.get((x, z))
                    if not col:
                        continue
                    if mode == "slice":
                        if y in col:
                            out.append([x, z, y, col[y]])
                    else:
                        best = None
                        for yy, i in col.items():
                            if self.names[i] != "air" and (best is None or yy > best[0]):
                                best = (yy, i)
                        if best:
                            out.append([x, z, best[0], best[1]])
            return list(self.names), out

    def view3d(self, cx, cy, cz, r, ry, limit=30000):
        """Blocks for the 3D map: every non-air block in a box around (cx, cy, cz) that touches air or unknown space (the ones
        you could see), nearest first. Returns (names, [[x, y, z, name index], ...], truncated)."""
        out = []
        with self.lock:
            def solid(x, y, z):
                col = self.cols.get((x, z))
                return col is not None and y in col and self.names[col[y]] != "air"
            for x in range(cx - r, cx + r + 1):
                for z in range(cz - r, cz + r + 1):
                    col = self.cols.get((x, z))
                    if not col:
                        continue
                    for y, i in col.items():
                        if abs(y - cy) > ry or self.names[i] == "air":
                            continue
                        if solid(x + 1, y, z) and solid(x - 1, y, z) and solid(x, y + 1, z) and solid(x, y - 1, z) and solid(x, y, z + 1) and solid(x, y, z - 1):
                            continue
                        out.append([x, y, z, i])
            names = list(self.names)
        out.sort(key=lambda c: (c[0] - cx) ** 2 + (c[1] - cy) ** 2 + (c[2] - cz) ** 2)
        return names, out[:limit], len(out) > limit

    def clear(self):
        with self.lock:
            self.cols, self.names, self.index, self.count = {}, [], {}, 0


class Fleet:
    """What every turtle has told us lately, plus the commands waiting for them (thread-safe)."""
    OFFLINE_AFTER = 45          # seconds without a report
    MAX_TURTLES = 200
    MAX_PENDING = 30000

    def __init__(self):
        self.lock = threading.Lock()
        self.turtles = {}
        self.cmds = {}
        self.typed = {}                  # id -> (x, y, z, facing): start position typed in by the user
        self.world = WorldMap()
        self.goto = {}                   # id -> (right, up, forward, direction): where an agent should walk before it starts a job
        self.auto_sites, self.layout_cursor = {}, {}
        self.fsites = {}         # foreman id -> where its jobs go (offsets from the foreman's own start cell)
        self.next_anchor = {}            # id -> (x, y, z, facing): the start position of the job an agent was sent to
        self.jobs = {}                   # id -> {"slug", "box", "t", "running"}: jobs sent with dispatch()
        self.sent = {}                   # id -> time of the last order dispatch() gave it
        self.storage = {}                # id -> what a storage keeper last reported (items, chests, ...)
        self.orders = {}                 # id -> [(item, count)] asked for on the web page, not yet handed to the keeper
        self.planned = {}                # job name (lower case) -> (x, y, z, facing): start position given before the turtle exists
        self.events = []                 # the last things that reached the server: (time, text), newest last
        self.last_contact = None         # (time, address) of the last turtle report
        self.name_order = random.sample(NAME_LIST, len(NAME_LIST))      # a fresh shuffle every run, so the first name differs
        self.gods = {}                   # id -> name given from the list of Deadlock heroes (turtles that have no label of their own)
        self.on_anchor = None            # called (no arguments) when typed anchors change, so the app can save them

    # ---------------------------------------------------------------- reports
    def _put(self, tid, **fields):
        with self.lock:
            if tid not in self.turtles and len(self.turtles) >= self.MAX_TURTLES:
                return False
            t = self.turtles.setdefault(tid, {"id": tid, "first_seen": time.time(), "history": [], "pending": []})
            save = False
            run = fields.pop("run", None)
            if run is not None and run != t.get("run"):
                t["run"] = run
                t["fix0"], t["gps_anchor"] = None, None          # a new run starts from a new place: forget the old frame
                if tid in self.next_anchor:                      # an agent that was sent to a site: its job starts there
                    self.typed[tid] = self.next_anchor.pop(tid)
                    save = True
            if tid in self.jobs and fields.get("kind") not in (None, "agent"):
                self.jobs[tid]["running"] = True
            fix, rel = fields.pop("fix", None), fields.get("rel")
            if fields.get("msg") and fields["msg"] != t.get("msg"):
                t["history"] = (t["history"] + [(time.time(), fields["msg"])])[-12:]
            t.update(fields)
            t["last_seen"] = time.time()
            t["stop_sent"] = t.get("stop_sent", False) and not fields.get("done")
            if fix and rel:
                self._take_fix(t, rel, fix)
        self._flush(tid)
        if save and self.on_anchor:
            self.on_anchor()
        return True

    @staticmethod
    def _take_fix(t, rel, fix):
        t["fix"] = fix
        if t.get("fix0") is None:
            t["fix0"] = (rel, fix)
        elif t.get("gps_anchor") is None:
            rel0, g0 = t["fix0"]
            face = _solve_facing(rel0, g0, rel, fix)
            if face:
                w = local_to_world((0, 0, 0, face), rel)
                t["gps_anchor"] = (fix[0] - w[0], fix[1] - rel[1], fix[2] - w[2], face)

    def _anchor(self, t):
        """(x, y, z, facing, where it came from) of the start cell, or None."""
        if t.get("gps_anchor"):
            return t["gps_anchor"] + ("gps",)
        typed = self.typed.get(t["id"])
        if typed:
            if t.get("fix") and t.get("rel"):                    # a GPS fix gives the exact start even without a facing
                w = local_to_world((0, 0, 0, typed[3]), t["rel"])
                fx = t["fix"]
                return (fx[0] - w[0], fx[1] - t["rel"][1], fx[2] - w[2], typed[3], "gps+typed")
            return tuple(typed) + ("typed",)
        return None

    def world_pos(self, t):
        a = self._anchor(t)
        if not a or not t.get("rel"):
            return None
        return local_to_world(a[:4], t["rel"])

    def foreman_world(self):
        """World position (x, y, z) of the Foreman, or None while it has not reported a position the app can place."""
        with self.lock:
            for t in self.turtles.values():
                if t.get("kind") == "foreman":
                    wp = self.world_pos(t)
                    if wp:
                        return tuple(int(v) for v in wp)
        return None

    def report_status(self, p):
        """A report from an automation program (POST /status)."""
        if not isinstance(p, dict) or p.get("v") != 1 or not isinstance(p.get("id"), int):
            raise ValueError("not a Carve status report")
        x, y, z = _num(p.get("x")), _num(p.get("y")), _num(p.get("z"))
        extra = {}
        if "inv" in p:
            extra["inv"] = self._inv(p.get("inv"))                  # the Foreman's inventory and crafting queue, for the Foreman tab
        if "q" in p:
            extra["q"] = self._queue(p.get("q"))
        if "crafty" in p:
            extra["crafty"] = bool(p.get("crafty"))
        res = self._put(p["id"], label=_clip(p.get("label"), 40), name=_clip(p.get("name"), 60), **extra,
                        kind=_clip(p.get("kind") or "auto", 20), x=x, y=y, z=z, rel=(x, y, z),
                        fuel=_clip(p.get("fuel"), 12), msg=_clip(p.get("msg")), act=_clip(p.get("act"), 90), lf=_num(p.get("f"), 0), n=_num(p.get("n")),
                        total=_num(p.get("total")), done=bool(p.get("done")),
                        run=_num(p.get("run"), None) if p.get("run") is not None else None, fix=self._fix(p.get("gps")))
        self._apply_planned(p["id"])
        return res

    @staticmethod
    def _inv(v):
        out = []
        if isinstance(v, list):
            for e in v[:16]:
                if (isinstance(e, list) and len(e) == 3 and isinstance(e[0], (int, float)) and isinstance(e[1], str)
                        and isinstance(e[2], (int, float))):
                    out.append([int(e[0]), _clip(e[1], 60), int(e[2])])
        return out

    @staticmethod
    def _queue(v):
        out = []
        if isinstance(v, list):
            for e in v[:40]:
                if isinstance(e, dict) and e.get("s") in ("now", "wait", "todo", "done"):
                    out.append({"t": _clip(e.get("t"), 70), "s": e["s"]})
        return out

    def plan_position(self, name, x, y, z, face):
        """Give the start position of a job by name, before its turtle has reported. It is applied as soon as (or if) a turtle of
        that name is known and has no typed position yet. face=None forgets the plan."""
        key = (name or "").strip().lower()
        if face is None:
            self.planned.pop(key, None)
        else:
            if face not in FACINGS:
                raise ValueError("facing must be north, east, south or west")
            self.planned[key] = (int(x), int(y), int(z), face)
        for tid in list(self.turtles):
            self._apply_planned(tid)
        if self.on_anchor:
            self.on_anchor()

    def _apply_planned(self, tid):
        with self.lock:
            t = self.turtles.get(tid)
            plan = self.planned.get((t.get("name") or "").strip().lower()) if t else None
            if not plan or t.get("planned_used") == plan:
                return
            t["planned_used"] = plan
            if tid in self.typed and self.typed[tid] != plan and not t.get("planned_set"):
                return                                   # the user typed a position for this turtle by hand: keep it
            self.typed[tid] = plan
            t["planned_set"] = True
        self._flush(tid)
        if self.on_anchor:
            self.on_anchor()

    @staticmethod
    def _fix(v):
        if isinstance(v, list) and len(v) == 3 and all(isinstance(n, (int, float)) for n in v):
            return tuple(int(round(n)) for n in v)
        return None

    def report_update(self, p):
        """The progress report of a dig program (POST /update): keep just the summary."""
        if not isinstance(p, dict) or p.get("v") != 1 or not isinstance(p.get("id"), int):
            return False
        done = bool(p.get("done")) or bool(p.get("stopped"))
        msg = _clip(p.get("msg"))
        if p.get("stopped") and not msg.startswith("Stopped"):
            msg = "Stopped (resumes with: carve resume)"
        rel = (_num(p.get("rx"), _num(p.get("x"))), _num(p.get("ry"), _num(p.get("y"))), _num(p.get("rz"), _num(p.get("z"))))
        return self._put(p["id"], label=_clip(p.get("label"), 40), name=_clip(p.get("name"), 60), kind="dig",
                         x=_num(p.get("x")), y=_num(p.get("y")), z=_num(p.get("z")), rel=rel, fuel=_clip(p.get("fuel"), 12),
                         msg=msg, n=_num(p.get("mined")), total=_num(p.get("total")), done=done,
                         run=_num(p.get("run"), None) if p.get("run") is not None else None, fix=self._fix(p.get("gps")))

    # ---------------------------------------------------------------- the world map
    def report_map(self, p):
        """Blocks a scout has seen (POST /map): [[right, up, forward, "name"], ...] measured from its start."""
        if not isinstance(p, dict) or p.get("v") != 1 or not isinstance(p.get("id"), int) or not isinstance(p.get("cells"), list):
            raise ValueError("not a Carve map report")
        with self.lock:
            t = self.turtles.get(p["id"])
            if t is None:
                return False
            for c in p["cells"][:2000]:
                if isinstance(c, list) and len(c) == 4 and all(isinstance(n, int) for n in c[:3]):
                    t["pending"].append((c[0], c[1], c[2], _block_name(c[3])))
            del t["pending"][:-self.MAX_PENDING]
            placed = self._anchor(t) is not None
            first = t.get("map_state") != placed
            t["map_state"] = placed
            name = t.get("label") or t.get("name") or "turtle %d" % p["id"]
        if first:
            self.note("map cells from %s: %s" % (name, "placed on the map" if placed else
                                                 "WAITING - give it a start position (Colony tab, or Fleet tab > Set start position)"))
        self._flush(p["id"])
        return True

    def map_waiting(self):
        """Scouts whose map cells can't be drawn yet because their start position isn't known."""
        with self.lock:
            return [{"id": t["id"], "name": t.get("label") or t.get("name") or "turtle %d" % t["id"], "count": len(t["pending"])}
                    for t in self.turtles.values() if t["pending"] and not self._anchor(t)]

    def _flush(self, tid):
        """Turn a turtle's waiting map cells into world cells once its place in the world is known."""
        with self.lock:
            t = self.turtles.get(tid)
            if not t or not t["pending"]:
                return
            a = self._anchor(t)
            if not a:
                return
            cells, t["pending"] = t["pending"], []
        for x, y, z, name in cells:
            w = local_to_world(a[:4], (x, y, z))
            self.world.add(w[0], w[1], w[2], name)

    def set_anchor(self, tid, x, y, z, face):
        """The user says: turtle tid started at world (x, y, z) facing face."""
        if face not in FACINGS:
            raise ValueError("facing must be north, east, south or west")
        with self.lock:
            self.typed[tid] = (int(x), int(y), int(z), face)
        self._flush(tid)
        if self.on_anchor:
            self.on_anchor()

    def clear_anchor(self, tid):
        with self.lock:
            self.typed.pop(tid, None)
        if self.on_anchor:
            self.on_anchor()

    def note(self, text, turtle=False, addr=""):
        """Write a line in the debug log (what reached the server, and what it made of it)."""
        with self.lock:
            now = time.time()
            self.events.append((now, text))
            del self.events[:-80]
            if turtle:
                self.last_contact = (now, addr)

    def debug_text(self, n=25):
        with self.lock:
            lines = ["%s  %s" % (time.strftime("%H:%M:%S", time.localtime(t)), s) for t, s in self.events[-n:]]
            lc = self.last_contact
        head = ("Last report from a turtle: %d s ago, from %s." % (time.time() - lc[0], lc[1] or "?")) if lc else \
               "No turtle has contacted this server yet."
        return head + "\n" + ("\n".join(lines) if lines else "(nothing has reached the server since it started)")

    def god_name(self, tid):
        """The next unused Deadlock hero name for a turtle (in this run's random order), one per turtle, remembered. After the list: "<name> 2"."""
        with self.lock:
            if tid in self.gods:
                return self.gods[tid]
            used = set(self.gods.values()) | {t.get("label") for t in self.turtles.values()}
            name = None
            for n in range(1, 100):
                for g in self.name_order:
                    cand = g if n == 1 else "%s %d" % (g, n)
                    if cand not in used:
                        name = cand
                        break
                if name:
                    break
            self.gods[tid] = name
        if self.on_anchor:
            self.on_anchor()
        return name

    # ---------------------------------------------------------------- commands
    RUN_NAME = re.compile(r"[a-z0-9_\-]{1,40}")

    def command(self, tid, cmd, arg=""):
        """Queue a command for a turtle; it gets it in the answer to its next report.
        "stop" ends its program; "run <program>" starts a program on an idle agent turtle."""
        t = self.turtles.get(tid)
        if t is None:
            return False
        if cmd == "stop":
            text = "stop"
        elif cmd == "run" and isinstance(arg, str) and self.RUN_NAME.fullmatch(arg) and t.get("kind") == "agent":
            text = "run " + arg
        else:
            return False
        with self.lock:
            self.cmds[tid] = text
        return True

    def take_command(self, tid):
        with self.lock:
            cmd = self.cmds.pop(tid, "")
            if cmd == "stop" and tid in self.turtles:
                self.turtles[tid]["stop_sent"] = True
        return cmd

    def reply_for(self, tid):
        """The answer to a report: ok [command], then where this turtle is and who is nearby (world coordinates)."""
        cmd = self.take_command(tid)
        lines = ["ok " + cmd if cmd else "ok"]
        with self.lock:
            me0 = self.turtles.get(tid)
            unnamed = me0 is not None and not me0.get("label")
        if unnamed:
            lines.append("label " + self.god_name(tid).replace(" ", "_"))
        target = self.goto.pop(tid, None) if cmd.startswith("run") else None
        if target:
            lines.append("goto %d %d %d %d" % target)
        now = time.time()
        with self.lock:
            me = self.turtles.get(tid)
            mine = self.world_pos(me) if me else None
            if mine:
                lines.append("me %d %d %d" % mine)
                near = []
                for oid, o in self.turtles.items():
                    wp = self.world_pos(o) if oid != tid and now - o["last_seen"] <= self.OFFLINE_AFTER else None
                    if wp:
                        d = abs(wp[0] - mine[0]) + abs(wp[1] - mine[1]) + abs(wp[2] - mine[2])
                        near.append((d, oid, re.sub(r"[^A-Za-z0-9_\-]", "_", o.get("label") or o.get("name") or "turtle")[:20], wp))
                for d, oid, nm, wp in sorted(near)[:6]:
                    lines.append("peer %d %s %d %d %d" % ((oid, nm) + wp))
        return "\n".join(lines)

    def _job_active(self, tid, job, now):
        t = self.turtles.get(tid)
        if t is None:
            return False
        if not job["running"]:
            return now - job["t"] < 900                           # sent, not started yet (travelling)
        return t.get("kind") != "agent" and self.state_of(t, now) not in ("finished", "stopped")

    def dispatch(self, slug, foot, site, facing):
        """Send a job to the nearest idle agent. site = world (x, y, z) of the job's start cell, facing = which way
        it faces there, foot = the job's footprint (local box) or None. Returns the turtle id; raises ValueError
        with a plain-words reason when it can't."""
        if not self.RUN_NAME.fullmatch(slug or ""):
            raise ValueError("That is not a valid program name.")
        if facing not in FACINGS:
            raise ValueError("Facing must be north, east, south or west.")
        site = tuple(int(v) for v in site)
        now = time.time()
        with self.lock:
            box = world_box(site + (facing,), foot) if foot else None
            if box:
                for jid, job in list(self.jobs.items()):
                    if self._job_active(jid, job, now):
                        if boxes_overlap(box, job["box"]):
                            raise ValueError("That would overlap '%s' that turtle #%d is working on." % (job["slug"], jid))
                    else:
                        del self.jobs[jid]
            best = None
            idle = 0
            for tid, t in self.turtles.items():
                if t.get("kind") != "agent" or self.state_of(t, now) != "idle" or tid in self.cmds or now - self.sent.get(tid, 0) < 20:
                    continue
                idle += 1
                a, wp = self._anchor(t), self.world_pos(t)
                if not a or not wp:
                    continue
                d = abs(wp[0] - site[0]) + abs(wp[1] - site[1]) + abs(wp[2] - site[2])
                if best is None or d < best[0]:
                    best = (d, tid, a)
            if best is None:
                raise ValueError("No idle agent turtle with a known position%s. Start the Agent program on a turtle and set its "
                                 "start position (or use GPS)." % (" (%d idle, but none placed)" % idle if idle else ""))
            _d, tid, a = best
            lx, ly, lz = world_to_local(a[:4], site)
            self.cmds[tid] = "run " + slug
            self.sent[tid] = now
            self.goto[tid] = (lx, ly, lz, facing_code(a[3], facing))
            self.next_anchor[tid] = site + (facing,)
            if box:
                self.jobs[tid] = {"slug": slug, "box": box, "t": now, "running": False}
            else:
                self.jobs.pop(tid, None)
        return tid

    # ---------------------------------------------------------------- stations (jobs with chests) and haulers
    def stations(self):
        """Names of the jobs that have chests, for the hauler's drop-down lists."""
        with self.lock:
            return sorted({t.get("name", "") for t in self.turtles.values() if t.get("kind") in STATION_CHESTS and t.get("name")})

    def _chest_stand(self, name, default_side):
        """World cell of the block above a station's chest, or (None, reason)."""
        base, _, side = (name or "").partition(":")
        side = side.strip().lower() or default_side
        base = base.strip().lower()
        if side not in ("in", "out"):
            return None, "side must be in or out"
        found = False
        for t in self.turtles.values():
            if t.get("name", "").lower() != base or t.get("kind") not in STATION_CHESTS:
                continue
            found = True
            cell = STATION_CHESTS[t["kind"]].get(side)
            a = self._anchor(t)
            if cell and a:
                w = local_to_world(a[:4], cell)
                return (w[0], w[1] + 1, w[2]), ""
        if found:
            return None, "'%s' has no known position (set its start position)" % name
        return None, "no job called '%s' has reported in" % name

    def route(self, tid, legs):
        """For a hauler: where to stand to take from / give to each leg's stations, in the hauler's own frame.
        Lines: 'leg N fx fy fz tx ty tz' or 'leg N ? reason'."""
        lines = []
        with self.lock:
            h = self.turtles.get(tid)
            a = self._anchor(h) if h else None
            for i, leg in enumerate(legs[:8], 1):
                if not a:
                    lines.append("leg %d ? the hauler's own start position is unknown" % i)
                    continue
                ends, why = [], ""
                for key, side in (("from", "out"), ("to", "in")):
                    w, why = self._chest_stand(str(leg.get(key, "")), side)
                    if w is None:
                        break
                    ends.append(world_to_local(a[:4], w))
                if why or len(ends) < 2:
                    lines.append("leg %d ? %s" % (i, why or "unknown"))
                else:
                    lines.append("leg %d %d %d %d %d %d %d" % ((i,) + tuple(ends[0]) + tuple(ends[1])))
        return "\n".join(lines)

    # ---------------------------------------------------------------- the foreman (sets up the other turtles)
    @staticmethod
    def _setup_jobs(jobs):
        """Validate the job list a foreman sends: [{name, slug, kind, furnaces, foot}]."""
        if not isinstance(jobs, list) or len(jobs) > 16:
            raise ValueError("bad job list")
        out = []
        for j in jobs:
            if not isinstance(j, dict) or not isinstance(j.get("name"), str) or not re.fullmatch(r"[A-Za-z0-9 _.:\-]{1,40}", j["name"]):
                raise ValueError("bad job name")
            if not isinstance(j.get("slug"), str) or not Fleet.RUN_NAME.fullmatch(j["slug"]):
                raise ValueError("bad program name")
            foot = j.get("foot")
            if foot is not None and not (isinstance(foot, list) and len(foot) == 6 and all(isinstance(v, int) for v in foot)):
                raise ValueError("bad footprint")
            fur = j.get("furnaces", 0)
            out.append({"name": j["name"], "slug": j["slug"], "kind": str(j.get("kind", "")), "foot": foot,
                        "furnaces": fur if isinstance(fur, int) and 0 <= fur <= 16 else 0})
        return out

    def _auto_site(self, ftid, job):
        """No position was given for this job: put it in a row to the right of the foreman, one footprint after the other."""
        key = job["name"].strip().lower()
        if key in self.planned or key in self.auto_sites:
            return
        a = self._anchor(self.turtles[ftid]) if ftid in self.turtles else None
        if not a:
            return
        foot = job.get("foot") or [-1, -1, -1, 1, 1, 1]
        cur = self.layout_cursor.get(ftid, 6)
        right = cur - foot[0]
        w = local_to_world(a[:4], (right, 0, 6))
        self.auto_sites[key] = (w[0], w[1], w[2], a[3])
        self.layout_cursor[ftid] = right + foot[3] + 1 + 3

    # v8.1: the Foreman's jobs are placed from the Foreman's own start cell. Typed coordinates in the Colony tab (an old, far away one sent a turtle 300 blocks off) are not used here.
    def _foreman_site(self, ftid, job):
        """Where a foreman's job goes: always an offset from the foreman itself (right and ahead of it, one footprint after the
        other with 10 blocks between), never a typed coordinate. Remembered per foreman start position."""
        a = self._anchor(self.turtles[ftid]) if ftid in self.turtles else None
        if not a:
            return None
        st = self.fsites.get(ftid)
        if not st or st["anchor"] != a[:4]:
            st = self.fsites[ftid] = {"anchor": a[:4], "cursor": 8, "sites": {}}
        key = job["name"].strip().lower()
        if key not in st["sites"]:
            foot = job.get("foot") or [-1, -1, -1, 1, 1, 1]
            right = st["cursor"] - foot[0]
            w = local_to_world(a[:4], (right, 0, 8))
            st["sites"][key] = (w[0], w[1], w[2], a[3])
            st["cursor"] = right + foot[3] + 1 + 10
        return st["sites"][key]

    def _job_site(self, name):
        """(x, y, z, facing) of a job's start cell by its name: the planned position, else the anchor of a turtle of that name."""
        key = name.strip().lower()
        if key in self.planned:
            return self.planned[key]
        if key in self.auto_sites:
            return self.auto_sites[key]
        for t in self.turtles.values():
            if (t.get("name") or "").strip().lower() == key:
                a = self._anchor(t)
                if a:
                    return a[:4]
        return None

    def setup_plan(self, tid, jobs):
        """For a foreman: the chests and furnaces to place, as cells to stand on (the foreman's own frame).
        Lines: 'chest NAME x y z', 'furnace NAME x y z', 'skip NAME reason', 'error reason'."""
        jobs = self._setup_jobs(jobs)
        lines = []
        with self.lock:
            f = self.turtles.get(tid)
            a = self._anchor(f) if f else None
            if not a:
                return "error my own start position is unknown (set it in the Fleet or Colony tab, or use GPS)"
            for j in jobs:
                cells = [("chest", c) for c in STATION_CHESTS.get(j["kind"], {}).values()]
                if j["kind"] == "smelter":
                    cells += [("furnace", (k, 0, 2)) for k in range(j["furnaces"])]
                if not cells:
                    continue
                site = self._foreman_site(tid, j)
                if not site:
                    lines.append("skip %s no start position yet" % j["name"])
                    continue
                for what, rel in cells:
                    w = local_to_world(site, rel)
                    lx, ly, lz = world_to_local(a[:4], (w[0], w[1] + 1, w[2]))
                    lines.append("%s %s %d %d %d" % (what, j["name"], lx, ly, lz))
        return "\n".join(lines) or "ok"

    def setup_spawn(self, tid, turtle_id, rel):
        """A foreman built a new turtle `rel` (right, up, forward) from its own start cell: the new turtle's start position is known
        from then on (it was placed facing the way the foreman faces)."""
        if not (isinstance(rel, list) and len(rel) == 3 and all(isinstance(v, int) for v in rel)) or not isinstance(turtle_id, int):
            raise ValueError("bad spawn")
        with self.lock:
            f = self.turtles.get(tid)
            a = self._anchor(f) if f else None
        if not a:
            raise ValueError("the foreman's own start position is unknown")
        w = local_to_world(a[:4], tuple(rel))
        self.set_anchor(turtle_id, w[0], w[1], w[2], a[3])
        return "ok"

    def setup_ready(self, turtle_id):
        """Has this new turtle started its agent program and reported in?"""
        with self.lock:
            t = self.turtles.get(turtle_id)
            ok = bool(t) and t.get("kind") == "agent" and self.state_of(t, time.time()) == "idle"
        return "ready" if ok else "wait"

    def setup_dispatch(self, tid, jobs):
        """For a foreman: hand every job to the nearest idle agent. Lines: 'sent NAME id' or 'fail NAME reason'."""
        jobs = self._setup_jobs(jobs)
        lines = []
        for j in jobs:
            with self.lock:
                site = self._foreman_site(tid, j)
            if not site:
                lines.append("fail %s no start position" % j["name"])
                continue
            try:
                lines.append("sent %s %d" % (j["name"], self.dispatch(j["slug"], j["foot"], site[:3], site[3])))
            except ValueError as e:
                lines.append("fail %s %s" % (j["name"], str(e)[:60]))
        return "\n".join(lines) or "ok"

    # ---------------------------------------------------------------- storage keepers
    _ITEM = re.compile(r"[a-z0-9_:.\-]{1,60}$")

    def report_storage(self, p):
        """What a storage keeper holds (POST /storage). Answers with the orders waiting for it: 'order <count> <item>' lines."""
        if not isinstance(p, dict) or p.get("v") != 1 or not isinstance(p.get("id"), int) or not isinstance(p.get("items"), dict):
            raise ValueError("not a storage report")
        items = {}
        for k, v in list(p["items"].items())[:2000]:
            if isinstance(k, str) and self._ITEM.match(k) and isinstance(v, (int, float)) and 0 < v < 10 ** 9:
                items[k] = int(v)
        with self.lock:
            self.storage[p["id"]] = {"id": p["id"], "name": _clip(p.get("name"), 60), "items": items, "seen": time.time(),
                                     "chests": _num(p.get("chests")), "max": _num(p.get("max")), "stacks": _num(p.get("stacks")),
                                     "slots": _num(p.get("slots")), "spare": _num(p.get("spare"))}
            todo = self.orders.pop(p["id"], [])
        return "\n".join("order %d %s" % (c, i) for i, c in todo) or "ok"

    def storage_view(self):
        """For the web page: every keeper, and the items of all of them added up."""
        now = time.time()
        with self.lock:
            keepers, total = [], {}
            for tid, st in sorted(self.storage.items()):
                keepers.append({"id": tid, "name": st["name"], "chests": st["chests"], "max": st["max"], "stacks": st["stacks"],
                                "slots": st["slots"], "spare": st["spare"], "age": round(now - st["seen"], 1),
                                "waiting": len(self.orders.get(tid, []))})
                for item, c in st["items"].items():
                    e = total.setdefault(item, {"item": item, "count": 0, "keepers": {}})
                    e["count"] += c
                    e["keepers"][str(tid)] = c
            return {"keepers": keepers, "items": sorted(total.values(), key=lambda e: e["item"])}

    def order_item(self, item, count, keeper=None):
        """Ask a keeper to put `count` of `item` in its pickup chest (POST /order)."""
        if not isinstance(item, str) or not self._ITEM.match(item):
            raise ValueError("bad item")
        try:
            count = int(count)
        except (TypeError, ValueError):
            raise ValueError("bad count")
        if not 1 <= count <= 4096:
            raise ValueError("count must be between 1 and 4096")
        with self.lock:
            best = None
            for tid, st in self.storage.items():
                have = st["items"].get(item, 0)
                if keeper is not None and tid != keeper:
                    continue
                if have > 0 and (best is None or have > best[0]):
                    best = (have, tid)
            if best is None:
                raise ValueError("nothing like that is in storage")
            q = self.orders.setdefault(best[1], [])
            if len(q) >= 40:
                raise ValueError("that keeper has too many orders waiting")
            q.append((item, min(count, best[0])))
            return best[1]

    def forget(self, tid):
        with self.lock:
            self.storage.pop(tid, None)
            self.orders.pop(tid, None)
            self.turtles.pop(tid, None)
            self.cmds.pop(tid, None)
            self.goto.pop(tid, None)
            self.next_anchor.pop(tid, None)
            self.jobs.pop(tid, None)

    @staticmethod
    def state_of(t, now):
        msg = t.get("msg", "")
        if msg.startswith("Stopped"):
            return "stopped"
        if t.get("done"):
            return "finished"
        if now - t["last_seen"] > Fleet.OFFLINE_AFTER:
            return "offline"
        if t.get("stop_sent"):
            return "stopping"
        if msg.startswith("Error"):
            return "error"
        if t.get("kind") == "agent" and msg.startswith("Idle"):
            return "idle"
        if _ATTENTION.search(msg):
            return "attention"
        return "working"

    @staticmethod
    def _compass(anchor, code):
        """The world direction a turtle faces now: code is its own direction (1 = the way its start faced, 2 = right, 3 = back, 4 = left)."""
        if not anchor or code not in (1, 2, 3, 4):
            return ""
        order = ["north", "east", "south", "west"]
        return order[(order.index(anchor[3]) + int(code) - 1) % 4]

    def snapshot(self, now=None):
        now = time.time() if now is None else now
        with self.lock:
            rows = []
            for tid in sorted(self.turtles):
                t = self.turtles[tid]
                a = self._anchor(t)
                wp = self.world_pos(t)
                rows.append({"id": tid, "label": t.get("label", ""), "name": t.get("name", ""), "kind": t.get("kind", ""),
                             "x": t.get("x", 0), "y": t.get("y", 0), "z": t.get("z", 0), "fuel": t.get("fuel", ""),
                             "msg": t.get("msg", ""), "act": t.get("act", ""), "dir": self._compass(a, t.get("lf")),
                             "n": t.get("n", 0), "total": t.get("total", 0),
                             "state": self.state_of(t, now), "age": round(now - t["last_seen"], 1),
                             "world": list(wp) if wp else None, "anchor": a[4] if a else "",
                             "facing": a[3] if a else ""})
                if t.get("inv") is not None:
                    rows[-1]["inv"] = t["inv"]
                if t.get("q") is not None:
                    rows[-1]["q"] = t["q"]
                if t.get("crafty") or t.get("kind") == "foreman":
                    rows[-1]["crafty"] = True
            # v7.8: two turtles with the same name get (1), (2) so they can be told apart on the page.
            seen = {}
            for r in rows:                                      # two turtles with the same name: number them so they can be told apart
                seen.setdefault((r["label"] or r["name"]).lower(), []).append(r)
            for group in seen.values():
                if len(group) > 1:
                    for i, r in enumerate(group, 1):
                        r["label"] = "%s (%d)" % (r["label"] or r["name"], i)
        return rows
# Talks to the GitHub API: uploads turtle programs and designs, lists them, removes them. Uses a token the user pastes in; it is only kept if they opt in.
# ===================================================================== GitHub
class UploadError(Exception):
    pass


INDEX_NAME = "index.json"


def _gh_request(method, url, token, body=None, timeout=20):
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    if token:
        req.add_header("Authorization", "Bearer " + token)
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("X-GitHub-Api-Version", "2022-11-28")
    req.add_header("User-Agent", "carve-designer")
    if data is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8") or "{}"
            return resp.status, json.loads(raw)
    except urllib.error.HTTPError as e:
        try:
            payload = json.loads(e.read().decode("utf-8"))
        except Exception:
            payload = {}
        return e.code, payload
    except urllib.error.URLError as e:
        why = str(e.reason)
        if "CERTIFICATE_VERIFY_FAILED" in why:
            why += (" -- on macOS run 'Install Certificates.command' from your Python "
                    "folder in Applications, then try again.")
        raise UploadError("Could not reach GitHub: %s" % why)


def _explain(status, info):
    msg = info.get("message", "") if isinstance(info, dict) else ""
    hints = {
        401: "GitHub rejected the token (wrong, expired or revoked).",
        403: "The token isn't allowed to write there. Give it 'Contents: Read and write' "
             "on this repository (or the 'repo' scope for a classic token).",
        404: "Repository or branch not found, or the token can't see it. Check the "
             "owner/name, the branch, and that the token has access to this repo.",
        409: "Conflict: the file changed on GitHub while uploading. Try again.",
        422: "GitHub refused the request (does the branch exist?).",
    }
    return "GitHub error %d: %s %s" % (status, hints.get(status, ""), ("(" + msg + ")") if msg else "")


def _file_url(api, repo, path):
    return "%s/repos/%s/contents/%s" % (api or GITHUB_API, repo, urllib.parse.quote(path))


def raw_url(repo, ref, path):
    return "https://raw.githubusercontent.com/%s/%s/%s" % (
        repo, urllib.parse.quote(ref, safe="/"), urllib.parse.quote(path))


def gh_read(repo, branch, path, token, api=None):
    """Returns (bytes, sha) for a file, or (None, None) if it doesn't exist."""
    status, info = _gh_request("GET", _file_url(api, repo, path) + "?ref=" + urllib.parse.quote(branch), token)
    if status == 200 and isinstance(info, dict) and "sha" in info:
        data = None
        if info.get("encoding") == "base64":
            data = base64.b64decode(info.get("content") or "")
        return data, info["sha"]
    if status == 404:
        return None, None
    raise UploadError(_explain(status, info))


def gh_write(repo, branch, path, token, content, message, api=None, skip_same=False):
    """Create or update one file. With skip_same, an identical file makes no new commit."""
    if not token:
        raise UploadError("Enter a GitHub token.")
    data, sha = gh_read(repo, branch, path, token, api)
    if skip_same and data is not None and data == content:
        return {"changed": False, "updated": True, "commit_sha": None, "html_url": "", "sha": sha}
    body = {"message": message, "branch": branch, "content": base64.b64encode(content).decode("ascii")}
    if sha:
        body["sha"] = sha
    status, info = _gh_request("PUT", _file_url(api, repo, path), token, body)
    if status not in (200, 201):
        raise UploadError(_explain(status, info))
    return {"changed": True, "updated": sha is not None, "commit_sha": info["commit"]["sha"],
            "html_url": (info.get("content") or {}).get("html_url", ""),
            "sha": (info.get("content") or {}).get("sha")}


def gh_delete(repo, branch, path, token, message, api=None):
    data, sha = gh_read(repo, branch, path, token, api)
    if sha is None:
        return False
    status, info = _gh_request("DELETE", _file_url(api, repo, path), token,
                               {"message": message, "sha": sha, "branch": branch})
    if status != 200:
        raise UploadError(_explain(status, info))
    return True


def gh_check(repo, token, api=None):
    status, info = _gh_request("GET", "%s/repos/%s" % (api or GITHUB_API, repo), token)
    if status != 200:
        raise UploadError(_explain(status, info))
    return {"private": bool(info.get("private")), "push": bool((info.get("permissions") or {}).get("push")),
            "default_branch": info.get("default_branch", "main")}


GALLERY_HTML = '''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Carve designs</title>
<style>
:root{--bg:#14171a;--card:#1d2227;--line:#323941;--text:#e6edf3;--dim:#8b949e;--accent:#f0a030}
body{margin:0;background:var(--bg);color:var(--text);font:15px/1.45 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}
main{max-width:980px;margin:0 auto;padding:28px 16px 60px}
h1{margin:0 0 4px;font-size:26px}p.sub{color:var(--dim);margin:0 0 22px}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:14px}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:14px 16px}
.card h2{margin:0 0 4px;font-size:17px}.meta{color:var(--dim);font-size:13px}
code{display:block;background:#0e1114;border:1px solid var(--line);border-radius:8px;padding:6px 9px;margin:10px 0;font-size:13px}
a.btn{display:inline-block;background:var(--accent);color:#1a1205;font-weight:600;border-radius:8px;padding:7px 14px;text-decoration:none}
#none{color:var(--dim)}
</style></head><body><main>
<h1>Carve designs</h1>
<p class="sub">Pick one to watch the turtle dig it in 3D. Made with Carve Designer.</p>
<div class="grid" id="grid"></div><p id="none">Loading...</p>
</main>
<script>
fetch("index.json",{cache:"no-store"}).then(function(r){return r.json();}).then(function(idx){
  var g=document.getElementById("grid"),list=idx.programs||[];
  document.getElementById("none").textContent=list.length?"":"No designs yet.";
  list.forEach(function(p){
    var c=document.createElement("div");c.className="card";
    var h=document.createElement("h2");h.textContent=p.name;c.appendChild(h);
    var m=document.createElement("div");m.className="meta";
    m.textContent=(p.size||[]).join(" x ")+"  -  "+p.blocks+" blocks"+(p.updated?"  -  "+p.updated.slice(0,10):"");c.appendChild(m);
    var k=document.createElement("code");k.textContent="carve "+p.slug;c.appendChild(k);
    var a=document.createElement("a");a.className="btn";a.href="view/"+p.slug+".html";a.textContent="Watch in 3D";c.appendChild(a);
    g.appendChild(c);
  });
}).catch(function(){document.getElementById("none").textContent="Could not load the list.";});
</script></body></html>
'''


def pages_url(repo, folder=""):
    """Where GitHub Pages serves the repo (folder included), with a trailing slash."""
    owner, name = repo.split("/", 1)
    base = "https://%s.github.io/" % owner.lower()
    if name.lower() != owner.lower() + ".github.io":
        base += name + "/"
    return base + (folder.strip("/") + "/" if folder else "")


def enable_pages(repo, branch, token, api=None):
    """Turn GitHub Pages on for the repo. Never raises: returns (ok, note)."""
    try:
        status, info = _gh_request("POST", "%s/repos/%s/pages" % (api or GITHUB_API, repo), token,
                                   {"source": {"branch": branch, "path": "/"}})
    except UploadError as ex:
        return False, str(ex)
    if status in (200, 201, 202, 204):
        return True, "GitHub Pages switched on (the first time it can take a minute or two to appear)."
    if status == 409:
        return True, ""
    msg = (info or {}).get("message", "") if isinstance(info, dict) else ""
    return False, "Could not switch on GitHub Pages (%s %s). In the repo: Settings > Pages > deploy from the %s branch." % (
        status, msg, branch)


def _settings(cfg):
    repo, branch, folder = check_repo_settings(cfg.get("repo"), cfg.get("branch"), cfg.get("folder"))
    return repo, branch, folder, (cfg.get("token") or "").strip()


def read_index(cfg, api=None):
    """The list of programs in the repo: {'version': 1, 'programs': [ {...}, ... ]}."""
    repo, branch, folder, token = _settings(cfg)
    data, _sha = gh_read(repo, branch, repo_path(folder, INDEX_NAME), token, api)
    try:
        idx = json.loads(data.decode("utf-8")) if data else {}
        progs = [p for p in idx.get("programs", []) if isinstance(p, dict)
                 and re.fullmatch(r"[a-z0-9_]+", str(p.get("slug", "")))]
    except Exception:
        progs = []
    return {"version": 1, "programs": progs}


def publish_design(cfg, design, live_url="", api=None):
    """Put one design in the repo: its turtle program, its editable source, the shared
    list (index.json) and the menu program (carve.lua). Other designs are left alone."""
    repo, branch, folder, token = _settings(cfg)
    if not token:
        raise UploadError("Enter a GitHub token.")
    _run, total, _skipped = build_run(design)
    if total == 0:
        raise UploadError("Nothing to mine in this design.")
    slug, name = design.slug(), clean_name(design.name)
    msg = "Carve: %s (%d blocks)" % (name, total)

    prog_path = repo_path(folder, "programs/%s.lua" % slug)
    r_prog = gh_write(repo, branch, prog_path, token, generate_lua(design, live_url).encode("utf-8"),
                      msg, api, skip_same=True)
    r_src = gh_write(repo, branch, repo_path(folder, "designs/%s.json" % slug), token,
                     json.dumps(design.to_json(), indent=1).encode("utf-8"), msg, api, skip_same=True)

    index = read_index(cfg, api)
    old = next((p for p in index["programs"] if p["slug"] == slug), {})
    entry = {"name": name, "slug": slug, "file": "programs/%s.lua" % slug,
             "design": "designs/%s.json" % slug, "size": [design.w, design.d, design.h],
             "blocks": total, "foot": design_footprint(design), "updated": old.get("updated", "")}
    if r_prog["changed"] or r_src["changed"] or not entry["updated"]:
        entry["updated"] = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    programs = [p for p in index["programs"] if p["slug"] != slug] + [entry]
    programs.sort(key=lambda p: str(p.get("name", "")).lower())
    gh_write(repo, branch, repo_path(folder, INDEX_NAME), token,
             json.dumps({"version": 1, "programs": programs}, indent=1).encode("utf-8"),
             "Carve: update list", api, skip_same=True)
    gh_write(repo, branch, repo_path(folder, "carve.lua"), token,
             generate_launcher(repo, branch, folder).encode("utf-8"), "Carve: menu program", api,
             skip_same=True)

    share = {}
    if cfg.get("share"):
        share = publish_share(cfg, design, repo, branch, folder, token, slug, msg, api)

    pinned = r_prog["commit_sha"] or branch
    return dict(share, **{
        "slug": slug, "name": name, "blocks": total, "count": len(programs),
        "changed": r_prog["changed"] or r_src["changed"],
        "launcher_url": raw_url(repo, branch, repo_path(folder, "carve.lua")),
        "program_url": raw_url(repo, pinned, prog_path),
        "html_url": r_prog["html_url"],
    })


def publish_share(cfg, design, repo, branch, folder, token, slug, msg, api=None):
    """The hosted pieces: a 3D replay page for this design, one shared copy of three.js, and a gallery page."""
    sim = simulate(design)
    info = {"slug": slug, "cmd": "carve " + slug, "gallery": "../index.html",
            "design": "../designs/%s.json" % slug}
    page = build_viewer_html(design, sim, share=info, external_three=True)
    gh_write(repo, branch, repo_path(folder, "view/%s.html" % slug), token, page.encode("utf-8"), msg, api, skip_same=True)
    gh_write(repo, branch, repo_path(folder, "view/three.min.js"), token, three_source().encode("utf-8"),
             "Carve: viewer library", api, skip_same=True)
    gh_write(repo, branch, repo_path(folder, "index.html"), token, GALLERY_HTML.encode("utf-8"),
             "Carve: gallery page", api, skip_same=True)
    ok, note = enable_pages(repo, branch, token, api)
    base = pages_url(repo, folder)
    return {"share_url": base + "view/%s.html" % slug, "gallery_url": base, "share_note": note, "pages_ok": ok}


def remove_design(cfg, slug, api=None):
    """Delete one program from the repo and from the list."""
    repo, branch, folder, token = _settings(cfg)
    if not re.fullmatch(r"[a-z0-9_]+", slug or ""):
        raise UploadError("Bad program name.")
    gh_delete(repo, branch, repo_path(folder, "programs/%s.lua" % slug), token, "Carve: remove " + slug, api)
    gh_delete(repo, branch, repo_path(folder, "designs/%s.json" % slug), token, "Carve: remove " + slug, api)
    gh_delete(repo, branch, repo_path(folder, "view/%s.html" % slug), token, "Carve: remove " + slug, api)
    gh_delete(repo, branch, repo_path(folder, "auto/%s.json" % slug), token, "Carve: remove " + slug, api)
    index = read_index(cfg, api)
    programs = [p for p in index["programs"] if p["slug"] != slug]
    gh_write(repo, branch, repo_path(folder, INDEX_NAME), token,
             json.dumps({"version": 1, "programs": programs}, indent=1).encode("utf-8"),
             "Carve: update list", api, skip_same=True)


def fetch_remote_design(cfg, slug, api=None):
    repo, branch, folder, token = _settings(cfg)
    if not re.fullmatch(r"[a-z0-9_]+", slug or ""):
        raise UploadError("Bad program name.")
    data, _ = gh_read(repo, branch, repo_path(folder, "designs/%s.json" % slug), token, api)
    if data is None:
        raise UploadError("That program has no saved design in the repo (it was uploaded by an older version).")
    return Design.from_json(json.loads(data.decode("utf-8")))


def turtle_commands(info):
    """The two lines to type on a turtle: install the menu, or fetch just this program."""
    return ("wget %s carve" % info["launcher_url"],
            "wget %s job_%s" % (info["program_url"], info["slug"]))


def design_from_link(url, timeout=20):
    """Open a design from the address of its shared page (.../view/<name>.html), its gallery
    entry, or the design file itself (.json)."""
    url = (url or "").strip()
    pu = urllib.parse.urlparse(url)
    if pu.scheme not in ("http", "https") or not pu.netloc:
        raise UploadError("That doesn't look like a web address.")
    path = pu.path
    m = re.search(r"/view/([a-z0-9_]+)\.html$", path)
    if m:
        path = path[:m.start()] + "/designs/%s.json" % m.group(1)
    elif not path.endswith(".json"):
        raise UploadError("Paste the address of a shared design page (it ends in /view/<name>.html).")
    target = urllib.parse.urlunparse((pu.scheme, pu.netloc, path, "", "", ""))
    req = urllib.request.Request(target, headers={"User-Agent": "carve-designer"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read(2_000_000)
        return Design.from_json(json.loads(raw.decode("utf-8")))
    except urllib.error.HTTPError as e:
        raise UploadError("The page said %s - is that the right address?" % e.code)
    except urllib.error.URLError as e:
        raise UploadError("Could not reach that address: %s" % e.reason)
    except (ValueError, KeyError, TypeError):
        raise UploadError("That address did not hold a Carve design.")


def publish_auto(cfg, job, live_url="", api=None):
    """Put one automation job (tree farm / smelter / crafter) in the repo next to the designs."""
    repo, branch, folder, token = _settings(cfg)
    if not token:
        raise UploadError("Enter a GitHub token.")
    try:
        job = clean_auto(job)
    except ValueError as ex:
        raise UploadError(str(ex))
    slug, name = auto_slug(job), job["name"]
    msg = "Carve: %s (%s)" % (name, dict(AUTO_KINDS)[job["kind"]].lower())
    prog_path = repo_path(folder, "programs/%s.lua" % slug)
    r_prog = gh_write(repo, branch, prog_path, token, generate_auto_lua(job, live_url).encode("utf-8"), msg, api, skip_same=True)
    r_src = gh_write(repo, branch, repo_path(folder, "auto/%s.json" % slug), token,
                     json.dumps(job, indent=1).encode("utf-8"), msg, api, skip_same=True)
    index = read_index(cfg, api)
    old = next((p for p in index["programs"] if p["slug"] == slug), {})
    entry = {"name": name, "slug": slug, "file": "programs/%s.lua" % slug, "auto": "auto/%s.json" % slug,
             "kind": job["kind"], "updated": old.get("updated", "")}
    if auto_footprint(job):
        entry["foot"] = auto_footprint(job)
    if r_prog["changed"] or r_src["changed"] or not entry["updated"]:
        entry["updated"] = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    programs = [p for p in index["programs"] if p["slug"] != slug] + [entry]
    programs.sort(key=lambda p: str(p.get("name", "")).lower())
    gh_write(repo, branch, repo_path(folder, INDEX_NAME), token,
             json.dumps({"version": 1, "programs": programs}, indent=1).encode("utf-8"),
             "Carve: update list", api, skip_same=True)
    gh_write(repo, branch, repo_path(folder, "carve.lua"), token,
             generate_launcher(repo, branch, folder).encode("utf-8"), "Carve: menu program", api, skip_same=True)
    pinned = r_prog["commit_sha"] or branch
    return {"slug": slug, "name": name, "kind": job["kind"], "blocks": 0, "count": len(programs),
            "changed": r_prog["changed"] or r_src["changed"],
            "launcher_url": raw_url(repo, branch, repo_path(folder, "carve.lua")),
            "program_url": raw_url(repo, pinned, prog_path), "html_url": r_prog["html_url"]}


def fetch_remote_auto(cfg, slug, api=None):
    repo, branch, folder, token = _settings(cfg)
    if not re.fullmatch(r"[a-z0-9_]+", slug or ""):
        raise UploadError("Bad program name.")
    data, _ = gh_read(repo, branch, repo_path(folder, "auto/%s.json" % slug), token, api)
    if data is None:
        raise UploadError("That program has no saved settings in the repo.")
    try:
        return clean_auto(json.loads(data.decode("utf-8")))
    except ValueError as ex:
        raise UploadError(str(ex))
# GUI part: the preview/animation of the dig route inside the main window.
# ======================================================================== GUI: viewer
SPEEDS = (1, 2, 4, 8, 16, 32, 64, 128, 256, 512)      # events per tick (25 ticks a second)
ARROWS = {1: "▲", 2: "▶", 3: "▼", 4: "◀"}


def fmt_time(seconds):
    seconds = int(seconds)
    if seconds < 90:
        return "%ds" % seconds
    if seconds < 5400:
        return "%d min" % round(seconds / 60.0)
    return "%.1f h" % (seconds / 3600.0)


class ViewMixin:
    """Preview (simulated route) and live (real turtle) viewing of one design, layer by layer."""

    # ---------------------------------------------------------------- tab
    def build_view_tab(self, f):
        pad = {"anchor": "w"}
        bold = ("TkDefaultFont", 10, "bold")
        ttk.Label(f, text="Preview the route", font=bold).pack(**pad)
        ttk.Label(f, text="Replays exactly how the turtle would dig this shape, layer by layer "
                          "(ignores trips to empty its inventory).", wraplength=300,
                  foreground="#555").pack(**pad)
        row = ttk.Frame(f)
        row.pack(fill="x", pady=(2, 2))
        ttk.Label(row, text="Turtle skin").pack(side="left")
        self.skin_box = ttk.Combobox(row, textvariable=self.skin_var, state="readonly", width=16,
                                     values=[label for _k, label in SKINS])
        self.skin_box.pack(side="left", padx=4)
        self.skin_box.bind("<<ComboboxSelected>>", lambda e: self.pick_skin())
        ttk.Button(row, text="Colours...", command=self.pick_skin_colors).pack(side="left")
        ttk.Button(f, text="Preview path", command=self.start_preview).pack(fill="x", pady=(4, 2))
        row = ttk.Frame(f)
        row.pack(fill="x", pady=(0, 6))
        ttk.Button(row, text="Open 3D view in browser", command=self.view3d).pack(side="left", fill="x", expand=True)
        ttk.Button(row, text="Save 3D page to share...", command=lambda: self.view3d(save=True)).pack(
            side="left", fill="x", expand=True, padx=(4, 0))
        ttk.Button(f, text="Record a video for Discord...", command=lambda: self.view3d(record=True)).pack(
            fill="x", pady=(0, 6))

        row = ttk.Frame(f)
        row.pack(fill="x")
        self.btn_restart = ttk.Button(row, text="|<", width=3, command=lambda: self.seek(0))
        self.btn_restart.pack(side="left")
        self.btn_play = ttk.Button(row, text="Play", width=7, command=self.play_toggle)
        self.btn_play.pack(side="left", padx=3)
        ttk.Label(row, text="speed").pack(side="left", padx=(6, 2))
        ttk.Scale(row, from_=1, to=10, variable=self.speed_var, length=110,
                  command=lambda v: self.speed_var.set(int(round(float(v))))).pack(side="left")
        self.seek_scale = ttk.Scale(f, from_=0, to=1, variable=self.seek_var, command=self.on_scale)
        self.seek_scale.pack(fill="x", pady=(6, 0))
        ttk.Checkbutton(f, text="Follow the turtle's layer", variable=self.follow_var).pack(**pad)
        ttk.Label(f, textvariable=self.info_var, wraplength=300, justify="left").pack(pady=(4, 0), **pad)
        ttk.Button(f, text="Back to editor", command=self.exit_view).pack(fill="x", pady=(6, 10))

        ttk.Separator(f).pack(fill="x", pady=4)
        ttk.Label(f, text="Live view (the real turtle)", font=bold).pack(**pad)
        row = ttk.Frame(f)
        row.pack(fill="x", pady=(2, 0))
        ttk.Label(row, text="Address").pack(side="left")
        ttk.Entry(row, textvariable=self.live_url_var, width=26).pack(side="left", padx=4)
        ttk.Checkbutton(f, text="Include live reporting in uploaded programs",
                        variable=self.live_enabled_var).pack(**pad)
        ttk.Checkbutton(f, text="Accept turtles from other computers (LAN)",
                        variable=self.lan_var).pack(**pad)
        row = ttk.Frame(f)
        row.pack(fill="x", pady=2)
        self.btn_listen = ttk.Button(row, text="Start listening", command=self.toggle_live)
        self.btn_listen.pack(side="left")
        ttk.Button(row, text="Show live view", command=self.show_live).pack(side="left", padx=4)
        ttk.Button(row, text="Next turtle", command=self.next_turtle).pack(side="left")
        ttk.Label(f, textvariable=self.live_status, wraplength=300, justify="left").pack(pady=(2, 0), **pad)
        ttk.Label(f, foreground="#555", wraplength=300, justify="left", text=(
            "The turtle must be allowed to reach this address. In Minecraft's "
            "computercraft-server.toml, find the [[http.rules]] entry with "
            "host = \"$private\" and set its action to \"allow\" (then restart the world). "
            "It does not work on servers you don't run yourself.")).pack(pady=(2, 0), **pad)

    # ---------------------------------------------------------------- entering / leaving
    def enter_view(self, kind, design, view=None, sim=None):
        self.stop_play()
        self.mode = kind
        self.vdesign = design
        self.view = view or ViewState(design)
        self.sim = sim
        run, _t, _s = build_run(design)
        hidden = {design.chest_cell} if (design.chest and design.chest_cell) else set()
        self.unreachable = design.sel - run - hidden
        self.layer = max(1, min(design.h, self.view.pos[1]))
        try:
            self.nb.select(self.tabs["Preview / Live"])
        except Exception:
            pass
        self.relayout(force=True)

    def exit_view(self):
        self.stop_play()
        if self.mode == "edit":
            return
        self.mode = "edit"
        self.vdesign = self.view = self.sim = None
        self.recompute()
        self.relayout(force=True)

    def skin_color(self, design=None):
        d = design or self.design
        return d.skin_body if d.skin == "custom" else SKIN_COLORS.get(d.skin, "#7ddc4a")

    def pick_skin(self, key=None):
        labels = {label: k for k, label in SKINS}
        key = key or labels.get(self.skin_var.get(), "crafty")
        if self.mode == "edit":
            self.snapshot()
        self.design.skin = key
        self.skin_var.set(dict(SKINS)[key])
        self.autosave()
        self.refresh_layer()

    def pick_skin_colors(self):
        from tkinter import colorchooser
        body = colorchooser.askcolor(color=self.design.skin_body, title="Body colour", parent=self.root)
        if not body or not body[1]:
            return
        accent = colorchooser.askcolor(color=self.design.skin_accent, title="Accent colour", parent=self.root)
        self.design.skin_body = body[1].lower()
        if accent and accent[1]:
            self.design.skin_accent = accent[1].lower()
        self.pick_skin("custom")

    # ---------------------------------------------------------------- 3D page
    def view3d(self, save=False, record=False):
        """Work out the route and show it in 3D in the web browser (or save it as a page to share)."""
        self.commit_name()
        design = (self.vdesign if self.mode != "edit" and self.vdesign is not None else self.design).copy()
        if build_run(design)[1] == 0:
            self.info("Nothing to show", "Select some cells connected to the turtle first.")
            return
        path = None
        if save:
            path = self.ask_save_path(defaultextension=".html", initialfile=design.slug() + "_3d.html",
                                      filetypes=[("Web page", "*.html")])
            if not path:
                return
        self.info_var.set("Building the 3D view...")

        def work():
            sim = simulate(design)
            page = build_viewer_html(design, sim)
            target = path or os.path.join(tempfile.gettempdir(), "carve_3d_%s.html" % design.slug())
            with open(target, "w", encoding="utf-8", newline="\n") as fh:
                fh.write(page)
            return target

        def done(target):
            self.info_var.set(("Saved %s - send that one file to anyone; it opens in any browser." % target)
                              if save else ("Opened in your browser: pick a length and press Start recording, then "
                                            "keep that tab in front until it finishes." if record
                                            else "Opened the 3D view in your browser."))
            try:
                webbrowser.open("file://" + urllib.request.pathname2url(os.path.abspath(target)) + ("#record" if record else ""))
            except Exception:
                pass

        self.run_bg(work, done, lambda ex: self.error("3D view", str(ex)))

    # ---------------------------------------------------------------- preview
    def start_preview(self):
        self.commit_name()
        design = self.design.copy()
        if build_run(design)[1] == 0:
            self.info("Nothing to preview", "Select some cells connected to the turtle first.")
            return
        self.info_var.set("Working out the route...")
        self.run_bg(lambda: simulate(design),
                    lambda sim: self.preview_ready(design, sim),
                    lambda ex: self.error("Preview", str(ex)))

    def preview_ready(self, design, sim):
        self.enter_view("preview", design, sim=sim)
        self.play_idx = 0
        self._scale_busy = True
        self.seek_scale.configure(to=max(1, len(sim.events)))
        self.seek_var.set(0)
        self._scale_busy = False
        self.after_view_change()

    def seek(self, k):
        if self.mode != "preview" or not self.sim:
            return
        evs = self.sim.events
        k = max(0, min(len(evs), int(k)))
        if k < self.play_idx:
            self.view = ViewState(self.vdesign)
            self.play_idx = 0
        for ev in evs[self.play_idx:k]:
            self.view.apply(ev)
        self.play_idx = k
        self._scale_busy = True
        self.seek_var.set(k)
        self._scale_busy = False
        self.after_view_change()

    def on_scale(self, _value):
        if not self._scale_busy and self.mode == "preview":
            self.seek(float(self.seek_var.get()))

    def play_toggle(self):
        if self.mode != "preview" or not self.sim:
            return
        if self.playing:
            self.stop_play()
            return
        if self.play_idx >= len(self.sim.events):
            self.seek(0)
        self.playing = True
        self.btn_play.configure(text="Pause")
        self._play_job = self.root.after(40, self.tick_play)

    def stop_play(self):
        self.playing = False
        if self._play_job is not None:
            try:
                self.root.after_cancel(self._play_job)
            except Exception:
                pass
            self._play_job = None
        try:
            self.btn_play.configure(text="Play")
        except Exception:
            pass

    def tick_play(self):
        self._play_job = None
        if not self.playing or self.mode != "preview":
            return
        step = SPEEDS[max(1, min(10, int(self.speed_var.get()))) - 1]
        self.seek(self.play_idx + step)
        if self.play_idx >= len(self.sim.events):
            self.stop_play()
            return
        self._play_job = self.root.after(40, self.tick_play)

    def after_view_change(self):
        v = self.view
        if self.follow_var.get() and v and v.pos[1] != self.layer:
            self.layer = max(1, min(self.sd().h, v.pos[1]))
        self.refresh_layer()
        if self.mode == "preview" and self.sim:
            n = len(self.sim.events)
            done = len(v.mined) - 1
            put = ("   placed %d / %d" % (len(v.placed), self.sim.places)) if self.sim.places else ""
            self.info_var.set(
                "Step %d / %d   dug %d / %d%s\nmoves %d (fuel)   whole job about %s, %d moves"
                % (self.play_idx, n, done, self.sim.total, put, v.moves,
                   fmt_time(self.sim.seconds), self.sim.moves))

    # ---------------------------------------------------------------- live
    def toggle_live(self):
        if self.server:
            self.stop_live()
        else:
            self.start_live()

    def start_live(self):
        url = normalize_live_url(self.live_url_var.get())
        if not url:
            self.error("Live view", "Use an address like  http://127.0.0.1:8765")
            return False
        port = urllib.parse.urlparse(url).port or 80
        self.cfg["live_url"] = url
        srv = LiveServer("0.0.0.0" if self.lan_var.get() else "127.0.0.1", port, self.live_q.put, self.fleet)
        try:
            srv.start()
        except OSError as ex:
            self.error("Live view", "Could not listen on port %d: %s" % (port, ex))
            return False
        self.server = srv
        self.btn_listen.configure(text="Stop listening")
        self.live_status.set("Listening on port %d. Start a turtle program that includes live "
                             "reporting, then press 'Show live view'." % srv.port)
        self.schedule_poll()
        if hasattr(self, "fleet_btn"):
            self.fleet_refresh()
        return True

    def stop_live(self):
        if self.live_job is not None:
            try:
                self.root.after_cancel(self.live_job)
            except Exception:
                pass
            self.live_job = None
        if self.server:
            self.server.stop()
            self.server = None
        self.btn_listen.configure(text="Start listening")
        self.live_status.set("Not listening.")
        if hasattr(self, "fleet_btn"):
            self.fleet_refresh()

    def schedule_poll(self):
        if self.live_job is None and self.server:
            self.live_job = self.root.after(100, self.poll_live)

    def poll_live(self):
        self.live_job = None
        if not self.server:
            return
        changed = False
        for _ in range(300):
            try:
                p = self.live_q.get_nowait()
            except queue.Empty:
                break
            changed = self.ingest(p) or changed
        if changed or self.mode == "live":
            self.live_refresh()
        self.schedule_poll()

    def ingest(self, p):
        """Fold one turtle report in. Returns True when it concerns the turtle being shown."""
        try:
            tid = int(p.get("id", 0))
            sess = self.sessions.get(tid) or LiveSession(tid)
            sess.apply(p)
        except (ValueError, KeyError, TypeError, AttributeError):
            return False
        self.sessions[tid] = sess
        if self.live_current is None:
            self.live_current = tid
        return tid == self.live_current

    def show_live(self):
        if not self.server and not self.start_live():
            return
        self.enter_view("live", self.design)
        self.live_refresh()

    def next_turtle(self):
        ids = sorted(self.sessions)
        if len(ids) > 1:
            i = ids.index(self.live_current) if self.live_current in ids else -1
            self.live_current = ids[(i + 1) % len(ids)]
            self.live_refresh()

    def live_refresh(self):
        sess = self.sessions.get(self.live_current)
        if sess is None:
            if self.server:
                self.live_status.set("Listening... no turtle has reported yet.")
            return
        others = len(self.sessions) - 1
        if sess.design is None:
            self.live_status.set("Turtle #%d is running; waiting for its next full report (up to 30 s)."
                                 % sess.id)
            return
        pct = int(100 * sess.count / sess.total) if sess.total else 100
        state = "FINISHED" if sess.done else ("stopped" if sess.stopped else sess.msg)
        put = ("   placed %d / %d" % (sess.placed_count, sess.placed_total)) if sess.placed_total else ""
        text = "Turtle #%d \"%s\"\n%d / %d dug (%d%%)%s   fuel %s\n%s%s" % (
            sess.id, sess.name, sess.count, sess.total, pct, put, sess.fuel, state,
            ("\n(+%d other turtle%s: 'Next turtle')" % (others, "s" if others > 1 else "")) if others else "")
        self.live_status.set(text)
        if self.mode != "live":
            return
        self.info_var.set(text)
        if self.view is not sess.view:               # a different run / design: rebuild the picture
            self.enter_view("live", sess.design, view=sess.view)
        self.after_view_change()
# GUI part: the GitHub tab and the 'Designs' window (this computer + the repository).
# ================================================================ GUI: GitHub + designs list
class GitMixin:
    """The GitHub tab and the 'Designs' window (this computer + the repo)."""

    # ---------------------------------------------------------------- tab
    def build_github_tab(self, f):
        bold = ("TkDefaultFont", 10, "bold")
        ttk.Label(f, text="Your GitHub repo", font=bold).pack(anchor="w")
        grid = ttk.Frame(f)
        grid.pack(fill="x")
        grid.columnconfigure(1, weight=1)
        for r, (label, var, show) in enumerate((
                ("Repo (owner/name)", self.repo_var, None), ("Branch", self.branch_var, None),
                ("Folder in repo", self.folder_var, None), ("Access token", self.token_var, "*"))):
            ttk.Label(grid, text=label).grid(row=r, column=0, sticky="w", pady=1)
            ttk.Entry(grid, textvariable=var, show=show, width=24).grid(row=r, column=1, sticky="ew", padx=(6, 0))
        ttk.Checkbutton(f, text="Remember token on this computer (stored unencrypted)",
                        variable=self.remember_var).pack(anchor="w")
        ttk.Checkbutton(f, text="Also publish a web page to share (3D replay + gallery)",
                        variable=self.share_var).pack(anchor="w")
        ttk.Label(f, foreground="#555", wraplength=300, justify="left", text=(
            "Use a PUBLIC repo so turtles can download without a login. Token: GitHub > Settings > "
            "Developer settings > Fine-grained tokens, limited to this repo, 'Contents: Read and write'. "
            "Every design is stored in its own file in the folder; the other designs stay untouched.")
                  ).pack(anchor="w", pady=(2, 6))
        row = ttk.Frame(f)
        row.pack(fill="x")
        ttk.Button(row, text="Upload to GitHub", command=self.upload).pack(side="left", fill="x", expand=True)
        ttk.Button(row, text="Test connection", command=self.test_connection).pack(side="left", fill="x", expand=True, padx=(4, 0))
        ttk.Label(f, text="Link to share", font=bold).pack(anchor="w", pady=(8, 0))
        row = ttk.Frame(f)
        row.pack(fill="x")
        ttk.Entry(row, textvariable=self.share_url_var, state="readonly", font=("TkFixedFont", 9)).pack(side="left", fill="x", expand=True)
        ttk.Button(row, text="Copy", command=lambda: self.copy_cmd(self.share_url_var)).pack(side="left", padx=(4, 0))
        ttk.Button(row, text="Open", command=self.open_share_url).pack(side="left", padx=(4, 0))
        ttk.Button(f, text="Open a design from a link...", command=self.open_from_link).pack(fill="x", pady=(3, 0))
        ttk.Label(f, text="Type this on the turtle", font=bold).pack(anchor="w", pady=(8, 0))
        self.cmd0_var, self.cmd1_var, self.cmd2_var = tk.StringVar(value="delete carve"), tk.StringVar(), tk.StringVar()
        for label, var in (("0. Resetting or updating the turtle? First:", self.cmd0_var),
                           ("1. Once - installs the menu:", self.cmd1_var), ("2. Then - runs this design:", self.cmd2_var)):
            ttk.Label(f, text=label, foreground="#555").pack(anchor="w", pady=(3, 0))
            row = ttk.Frame(f)
            row.pack(fill="x")
            ttk.Entry(row, textvariable=var, state="readonly", font=("TkFixedFont", 9)).pack(side="left", fill="x", expand=True)
            ttk.Button(row, text="Copy", command=lambda v=var: self.copy_cmd(v)).pack(side="left", padx=(4, 0))
        for v in (self.repo_var, self.branch_var, self.folder_var, self.name_var):
            v.trace_add("write", lambda *a: self.refresh_turtle_commands())
        self.refresh_turtle_commands()
        ttk.Button(f, text="Open designs on this PC / in the repo...", command=self.open_designs_window
                   ).pack(fill="x", pady=(6, 0))
        ttk.Button(f, text="Save this program as a .lua file...", command=self.save_lua_file
                   ).pack(fill="x", pady=(4, 0))
        ttk.Label(f, textvariable=self.gh_status, wraplength=300, justify="left").pack(anchor="w", pady=(6, 2))
        self.cmd_text = tk.Text(f, height=8, width=44, wrap="word", font=("TkFixedFont", 9))
        self.cmd_text.pack(fill="both", expand=True)

    def collect_github_cfg(self, need_token=True):
        try:
            repo, branch, folder = check_repo_settings(self.repo_var.get(), self.branch_var.get(),
                                                       self.folder_var.get())
        except UploadError as ex:
            self.gh_status.set(str(ex))
            return None
        token = self.token_var.get().strip() or os.environ.get("GITHUB_TOKEN", "").strip()
        if need_token and not token:
            self.gh_status.set("Enter your GitHub access token.")
            return None
        self.cfg.update(repo=repo, branch=branch, folder=folder,
                        live_enabled=bool(self.live_enabled_var.get()),
                        live_url=self.live_url_var.get().strip(), share=bool(self.share_var.get()))
        if self.remember_var.get() and token:
            self.cfg["token"] = token
        else:
            self.cfg.pop("token", None)
        save_config(self.cfg)
        return {"repo": repo, "branch": branch, "folder": folder, "token": token,
                "share": bool(self.share_var.get())}

    def live_url_for_upload(self):
        if not self.live_enabled_var.get():
            return ""
        url = normalize_live_url(self.live_url_var.get())
        if not url:
            self.gh_status.set("The live view address must look like  http://127.0.0.1:8765  "
                               "(or untick 'Include live reporting').")
            return None
        return url

    def upload(self):
        self.commit_name()
        cfg = self.collect_github_cfg()
        live_url = self.live_url_for_upload()
        if cfg is None or live_url is None:
            return
        design = self.design.copy()
        if build_run(design)[1] == 0:
            self.gh_status.set("Nothing to mine yet - select some cells connected to the turtle.")
            return
        self.gh_status.set("Uploading...")

        def work():
            info = publish_design(cfg, design, live_url)
            try:
                info["estimate"] = estimate(design)
            except Exception:
                info["estimate"] = None
            return info
        self.run_bg(work, self.upload_done,
                    lambda ex: self.gh_status.set(str(ex)))

    def upload_done(self, info):
        self.last_upload = info
        menu, prog = turtle_commands(info)
        self.refresh_turtle_commands()
        self.cmd2_var.set("carve %s" % info["slug"])
        self.root.clipboard_clear()
        self.root.clipboard_append(menu)
        self.gh_status.set("Uploaded \"%s\" (%d blocks). %d program%s in the repo now." % (
            info["name"], info["blocks"], info["count"], "" if info["count"] == 1 else "s")
            + ("" if info["changed"] else "  (no changes since last upload)")
            + "  The install command is copied - paste it into the turtle.")
        link = info.get("share_url", "")
        self.share_url_var.set(link)
        if link:
            self.root.clipboard_clear()
            self.root.clipboard_append(link)
            self.gh_status.set(self.gh_status.get().replace("The install command is copied - paste it into the turtle.",
                               "The share link is copied. %s" % info.get("share_note", "")).strip())
        est = info.get("estimate")
        if est and est["warnings"]:
            self.gh_status.set(self.gh_status.get() + "  Heads up: %d thing%s to check (below)." % (
                len(est["warnings"]), "" if len(est["warnings"]) == 1 else "s"))
        self.cmd_text.delete("1.0", "end")
        self.cmd_text.insert("1.0", ((estimate_text(est) + "\n\n") if est else "") + (
            "Resetting the turtle or updating the menu? Type this first:\ndelete carve\n\n"
            "On a turtle, once - installs the menu:\n%s\n\n"
            "Then, any time:\ncarve          (pick from the list)\ncarve %s\n\n"
            "Or fetch just this program:\n%s\nrun it with:  job_%s\n\n"
            "(If a file already exists on the turtle, type  delete <name>  first.)"
            % (menu, info["slug"], prog, info["slug"])))

    def open_share_url(self):
        url = self.share_url_var.get()
        if url:
            try:
                webbrowser.open(url)
            except Exception:
                pass
        else:
            self.gh_status.set("Upload a design with the web page option on first.")

    def open_from_link(self):
        from tkinter import simpledialog
        url = simpledialog.askstring("Open from link", "Paste the address of a shared design page:", parent=self.root)
        if not url:
            return
        self.gh_status.set("Fetching the design...")

        def done(design):
            self.exit_view()
            self.commit_name()
            design.name = unique_name(design.name, {e["slug"] for e in library_list()})
            self.set_design(design)
            self.gh_status.set("Opened \"%s\" from the link." % design.name)
        self.run_bg(lambda: design_from_link(url), done, lambda ex: self.gh_status.set(str(ex)))

    def refresh_turtle_commands(self):
        """Fill the two 'type this on the turtle' boxes from the repo settings and the design name."""
        if not hasattr(self, "cmd1_var"):
            return
        slug = slugify(self.name_var.get())
        try:
            repo, branch, folder = check_repo_settings(self.repo_var.get(), self.branch_var.get(), self.folder_var.get())
            self.cmd1_var.set("wget %s carve" % raw_url(repo, branch, repo_path(folder, "carve.lua")))
        except Exception:
            self.cmd1_var.set("(fill in the repo above first)")
        self.cmd2_var.set("carve %s" % slug)

    def copy_cmd(self, var):
        text = var.get()
        if text.startswith("("):
            return
        self.root.clipboard_clear()
        self.root.clipboard_append(text)
        self.gh_status.set("Copied: " + text)

    def copy_line(self, which):
        if not self.last_upload:
            self.gh_status.set("Upload a design first.")
            return
        line = turtle_commands(self.last_upload)[which]
        self.root.clipboard_clear()
        self.root.clipboard_append(line)
        self.gh_status.set("Copied: " + line)

    def test_connection(self):
        cfg = self.collect_github_cfg(need_token=False)
        if cfg is None:
            return
        self.gh_status.set("Checking...")

        def done(r):
            msgs = []
            if r["private"]:
                msgs.append("This repo is PRIVATE - turtles can't download from it. Make it public.")
            if cfg["token"] and not r["push"]:
                msgs.append("The token can't write to this repo.")
            self.gh_status.set(" ".join(msgs) or "Connected. The repo is public and the token can write.")

        self.run_bg(lambda: gh_check(cfg["repo"], cfg["token"]), done,
                    lambda ex: self.gh_status.set(str(ex)))

    def save_lua_file(self):
        self.commit_name()
        if build_run(self.design)[1] == 0:
            self.info("Nothing to mine", "Select some cells connected to the turtle first.")
            return
        live_url = self.live_url_for_upload()
        if live_url is None:
            return
        path = self.ask_save_path(defaultextension=".lua", initialfile="job_%s.lua" % self.design.slug(),
                                  filetypes=[("Lua program", "*.lua")])
        if path:
            with open(path, "w", encoding="utf-8", newline="\n") as f:
                f.write(generate_lua(self.design, live_url))
            self.gh_status.set("Saved " + path)

    # ---------------------------------------------------------------- designs window
    def open_designs_window(self):
        if self.dwin is not None:
            try:
                if self.dwin.winfo_exists():
                    self.dwin.lift()
                    self.refresh_local()
                    return
            except Exception:
                pass
        win = self.dwin = tk.Toplevel(self.root)
        win.title("Designs")
        frm = ttk.Frame(win, padding=10)
        frm.pack(fill="both", expand=True)
        frm.columnconfigure(0, weight=1)
        frm.columnconfigure(1, weight=1)
        ttk.Label(frm, text="On this computer", font=("TkDefaultFont", 10, "bold")).grid(row=0, column=0, sticky="w")
        ttk.Label(frm, text="In your GitHub repo", font=("TkDefaultFont", 10, "bold")).grid(row=0, column=1, sticky="w", padx=(10, 0))
        self.local_list = tk.Listbox(frm, width=38, height=14, exportselection=False)
        self.remote_list = tk.Listbox(frm, width=38, height=14, exportselection=False)
        self.local_list.grid(row=1, column=0, sticky="nsew")
        self.remote_list.grid(row=1, column=1, sticky="nsew", padx=(10, 0))
        b1 = ttk.Frame(frm)
        b1.grid(row=2, column=0, sticky="w", pady=4)
        ttk.Button(b1, text="Open", command=self.open_local).pack(side="left")
        ttk.Button(b1, text="Duplicate", command=self.duplicate_local).pack(side="left", padx=4)
        ttk.Button(b1, text="Delete", command=self.delete_local).pack(side="left")
        b2 = ttk.Frame(frm)
        b2.grid(row=2, column=1, sticky="w", pady=4, padx=(10, 0))
        ttk.Button(b2, text="Refresh", command=self.refresh_remote).pack(side="left")
        ttk.Button(b2, text="Open here", command=self.open_remote).pack(side="left", padx=4)
        ttk.Button(b2, text="Remove from repo", command=self.remove_remote).pack(side="left")
        ttk.Label(frm, textvariable=self.dstatus, wraplength=520, justify="left").grid(
            row=3, column=0, columnspan=2, sticky="w")
        self._local_entries, self._remote_entries = [], []
        self.refresh_local()
        self.dstatus.set("Press Refresh to list what is in the repo.")

    def _fmt(self, name, size, blocks):
        return "%s   %dx%dx%d, %s blocks" % (name, size[0], size[1], size[2], blocks)

    def _dwin_alive(self):
        try:
            return self.dwin is not None and bool(self.dwin.winfo_exists())
        except Exception:
            return False

    def refresh_local(self):
        if not self._dwin_alive():
            return
        self._local_entries = library_list()
        self.local_list.delete(0, "end")
        for e in self._local_entries:
            mark = "  *" if e["slug"] == self.design.slug() else ""
            self.local_list.insert("end", self._fmt(e["name"], e["size"], e["blocks"]) + mark)

    def _picked(self, listbox, entries):
        sel = listbox.curselection()
        return entries[sel[0]] if sel and sel[0] < len(entries) else None

    def open_local(self):
        e = self._picked(self.local_list, self._local_entries)
        if not e:
            return
        try:
            des = library_load(e["slug"])
        except Exception as ex:
            self.error("Open", "Could not read that design: %s" % ex)
            return
        self.exit_view()
        self.set_design(des)
        self.refresh_local()

    def duplicate_local(self):
        e = self._picked(self.local_list, self._local_entries)
        if not e:
            return
        try:
            des = library_load(e["slug"])
        except Exception as ex:
            self.error("Duplicate", str(ex))
            return
        des.name = unique_name(des.name + " copy", {x["slug"] for x in library_list()})
        library_save(des)
        self.refresh_local()

    def delete_local(self):
        e = self._picked(self.local_list, self._local_entries)
        if not e or not self.confirm("Delete design", "Delete '%s' from this computer?\n"
                                     "(Copies already uploaded to GitHub are not touched.)" % e["name"]):
            return
        library_delete(e["slug"])
        if e["slug"] == self.design.slug():
            rest = library_list()
            if rest:
                self.set_design(library_load(rest[0]["slug"]))
            else:
                self.new_design()
        self.refresh_local()

    def refresh_remote(self):
        cfg = self.collect_github_cfg(need_token=False)
        if cfg is None:
            self.dstatus.set(self.gh_status.get())
            return
        self.dstatus.set("Asking GitHub...")

        def done(index):
            self._remote_entries = index["programs"]
            if not self._dwin_alive():
                return
            self.remote_list.delete(0, "end")
            for p in self._remote_entries:
                size = p.get("size") or [0, 0, 0]
                if p.get("kind"):
                    label = dict(AUTO_KINDS).get(p["kind"], p["kind"])
                    self.remote_list.insert("end", "%s   (%s)" % (p.get("name", p["slug"]), label.lower()))
                else:
                    self.remote_list.insert("end", self._fmt(p.get("name", p["slug"]), size, p.get("blocks", "?")))
            self.dstatus.set("%d program(s) in %s/%s" % (len(self._remote_entries), cfg["repo"],
                                                         cfg["folder"] or ""))

        self.run_bg(lambda: read_index(cfg), done, lambda ex: self.dstatus.set(str(ex)))

    def open_remote(self):
        e = self._picked(self.remote_list, self._remote_entries)
        cfg = self.collect_github_cfg(need_token=False)
        if not e or cfg is None:
            return
        self.dstatus.set("Downloading...")
        if e.get("kind"):
            def done_auto(job):
                self.auto_load(job)
                self.dstatus.set("Loaded '%s' into the Automation tab." % job["name"])
                self.show_tab("Automation")
            self.run_bg(lambda: fetch_remote_auto(cfg, e["slug"]), done_auto, lambda ex: self.dstatus.set(str(ex)))
            return

        def done(des):
            taken = {x["slug"] for x in library_list()}
            if des.slug() in taken:
                des.name = unique_name(des.name + " (repo)", taken)
            library_save(des)
            self.exit_view()
            self.set_design(des)
            self.refresh_local()
            self.dstatus.set("Opened '%s' as a new design on this computer." % des.name)

        self.run_bg(lambda: fetch_remote_design(cfg, e["slug"]), done, lambda ex: self.dstatus.set(str(ex)))

    def remove_remote(self):
        e = self._picked(self.remote_list, self._remote_entries)
        cfg = self.collect_github_cfg()
        if not e or cfg is None:
            self.dstatus.set(self.gh_status.get() if cfg is None else "")
            return
        if not self.confirm("Remove from repo", "Remove '%s' from the GitHub repo?\n"
                            "Your copy on this computer stays." % e.get("name", e["slug"])):
            return
        self.dstatus.set("Removing...")
        self.run_bg(lambda: remove_design(cfg, e["slug"]),
                    lambda _r: (self.dstatus.set("Removed."), self.refresh_remote()),
                    lambda ex: self.dstatus.set(str(ex)))
# GUI part: the turtle inventory ('Blocks') tab and the item picture bank used by every tab.
# ============================================================ GUI: turtle inventory ("Blocks" tab)
class IconBank:
    """Pictures of vanilla items, drawn from our own simplified tiles (see item_tile). Anything it does not
    know (modded items) gets None, and the caller draws a coloured square instead."""

    def __init__(self, root):
        self.root = root
        self.cache = {}

    def known(self, item):
        return display_tile(item) is not None

    def names(self):
        names = set(icon_names())
        if TEX["mode"] == "imported":
            names |= set(pack_names())
        return sorted(names)

    def get(self, item, zoom=1):
        key = (item, zoom)
        if key in self.cache:
            return self.cache[key]
        tile = display_tile(item)
        if tile is None:
            return None
        img = tk.PhotoImage(master=self.root, width=16, height=16)
        for y, row in enumerate(tile):
            img.put("{" + " ".join("#%02x%02x%02x" % c if c else "#000000" for c in row) + "}", to=(0, y))
            for x, c in enumerate(row):
                if c is None:
                    img.transparency_set(x, y, True)
        if zoom > 1:
            big = tk.PhotoImage(master=self.root, width=16 * zoom, height=16 * zoom)
            big.tk.call(str(big), "copy", str(img), "-zoom", zoom, zoom)
            img = big
        self.cache[key] = img
        return img

    def swatch(self, item, size=16):
        key = ("sw", item, size)
        img = self.cache.get(key)
        if img is None:
            img = tk.PhotoImage(master=self.root, width=size, height=size)
            img.put("#101316", to=(0, 0, size, size))
            img.put(display_color(item), to=(1, 1, size - 1, size - 1))
            self.cache[key] = img
        return img

    def picture(self, item, zoom=1):
        return self.get(item, zoom) or self.swatch(item, 16 * zoom)


class BlocksMixin:
    """A little picture of the turtle's 16 slots. A slot with an item is reserved for placing:
    the turtle keeps that item there. Paint cells with a slot as the brush to make the turtle dig
    them out and then put that item in; torches can be spread over the floor automatically."""

    SLOT_PX = 62

    def icon_bank(self):
        if not hasattr(self, "_icons"):
            try:
                self._icons = IconBank(self.root)
            except Exception:
                self._icons = None          # no PNG support: coloured squares only
        return self._icons

    def build_blocks_tab(self, p):
        bold = ("TkDefaultFont", 10, "bold")
        ttk.Label(p, text="Turtle inventory", font=bold).pack(anchor="w")
        px = self.SLOT_PX
        self.inv_canvas = tk.Canvas(p, width=px * 4, height=px * 4, bg="#14171a", highlightthickness=0)
        self.inv_canvas.pack(anchor="w", pady=(2, 4))
        self.inv_canvas.bind("<ButtonPress-1>", self.inv_click)
        self.inv_canvas.bind("<Double-Button-1>", self.inv_double)
        ttk.Label(p, foreground="#666", wraplength=300, justify="left", text=(
            "Click a slot, then pick its item. A slot with an item is kept for placing "
            "(never dumped or burnt); empty slots hold what it digs up and its fuel."
        )).pack(anchor="w")

        self.slot_title = ttk.Label(p, text="", font=bold)
        self.slot_title.pack(anchor="w", pady=(6, 2))
        row = ttk.Frame(p)
        row.pack(fill="x")
        self.item_box = ttk.Combobox(row, textvariable=self.item_var, width=24,
                                     values=[n for n, _c in ITEM_PRESETS])
        self.item_box.pack(side="left")
        self.item_box.bind("<Return>", lambda e: self.set_slot_from_box())
        self.item_box.bind("<<ComboboxSelected>>", lambda e: self.set_slot_from_box())
        ttk.Button(row, text="Browse items...", command=self.open_picker).pack(side="left", padx=(6, 0))
        ttk.Button(row, text="Textures...", command=self.open_textures).pack(side="left", padx=(4, 0))
        row = ttk.Frame(p)
        row.pack(fill="x", pady=3)
        ttk.Button(row, text="Empty slot", command=self.empty_slot).pack(side="left")
        self.fav_btn = ttk.Button(row, text="Add to favorites", command=self.toggle_slot_favorite)
        self.fav_btn.pack(side="left", padx=4)
        ttk.Button(row, text="Paint with this", command=self.use_brush).pack(side="left")

        self.fav_title = ttk.Label(p, text="Favorites", font=bold)
        self.fav_title.pack(anchor="w", pady=(4, 1))
        self.fav_bar = ttk.Frame(p)
        self.fav_bar.pack(anchor="w", fill="x")
        self.fav_hint = tk.StringVar(value="")
        ttk.Label(p, textvariable=self.fav_hint, foreground="#666").pack(anchor="w")

        ttk.Label(p, textvariable=self.brush_var, foreground="#b35c00").pack(anchor="w", pady=(4, 0))
        ttk.Button(p, text="Back to plain digging", command=self.dig_only).pack(anchor="w", pady=(2, 6))

        ttk.Label(p, text="Torches", font=bold).pack(anchor="w")
        self.torch_box = ttk.Combobox(p, textvariable=self.torch_mode_var, state="readonly", width=34,
                                      values=[label for _k, label in TORCH_MODES])
        self.torch_box.pack(anchor="w", pady=(2, 0))
        self.torch_box.bind("<<ComboboxSelected>>", lambda e: self.pick_torch_mode())
        row = ttk.Frame(p)
        row.pack(fill="x", pady=2)
        ttk.Label(row, text="one every").pack(side="left")
        ttk.Spinbox(row, from_=1, to=16, width=3, textvariable=self.torch_gap).pack(side="left", padx=3)
        ttk.Label(row, text="cells on the floor").pack(side="left")
        row = ttk.Frame(p)
        row.pack(fill="x", pady=2)
        ttk.Button(row, text="Add torches", command=self.add_torches).pack(side="left")
        ttk.Button(row, text="Remove all placed blocks", command=self.clear_all_blocks).pack(side="left", padx=4)

        ttk.Label(p, textvariable=self.supply_var, justify="left", wraplength=300).pack(anchor="w", pady=(6, 0))

    # ------------------------------------------------------------------ drawing the slots
    def refresh_inventory(self):
        c = getattr(self, "inv_canvas", None)
        if c is None:
            return
        d = self.design
        if self.brush is not None and self.brush not in d.inv:
            self.brush = None
        need = supply_needs(d)
        c.delete("all")
        px = self.SLOT_PX
        for s in range(1, 17):
            col, row = (s - 1) % 4, (s - 1) // 4
            x0, y0 = col * px, row * px
            name = d.inv.get(s)
            c.create_rectangle(x0 + 2, y0 + 2, x0 + px - 2, y0 + px - 2,
                               fill="#2b3038" if name else "#1b1f24", outline="#3d444d")
            c.create_text(x0 + 7, y0 + 8, text=str(s), anchor="w", fill="#8b949e", font=("TkDefaultFont", 8))
            if name:
                bank = self.icon_bank()
                img = bank.get(name, 2) if bank else None
                if img is not None:
                    c.create_image(x0 + px // 2, y0 + 30, image=img)
                else:
                    c.create_rectangle(x0 + 19, y0 + 15, x0 + px - 19, y0 + px - 25,
                                       fill=item_color(name), outline="#0e1114")
                short = item_label(name)
                c.create_text(x0 + px / 2, y0 + px - 15, text=short[:10], fill="#e6edf3", font=("TkDefaultFont", 7))
                n = need.get(s, 0)
                c.create_text(x0 + px - 6, y0 + 8, text=("x%d" % n) if n else "", anchor="e",
                              fill="#ffd54a", font=("TkDefaultFont", 8, "bold"))
            else:
                c.create_text(x0 + px / 2, y0 + px / 2, text="free", fill="#4a525b", font=("TkDefaultFont", 8))
            if s == self.brush:
                c.create_rectangle(x0 + 2, y0 + 2, x0 + px - 2, y0 + px - 2, outline="#f0a030", width=3)
            if s == self.sel_slot:
                c.create_rectangle(x0 + 5, y0 + 5, x0 + px - 5, y0 + px - 5, outline="#6fb1ff", width=2)
        self.sync_options()
        cur = d.inv.get(self.sel_slot)
        self.slot_title.configure(text="Slot %d%s" % (self.sel_slot, ("  -  " + item_label(cur)) if cur else ""))
        self.item_var.set(cur or "")
        self.fav_btn.configure(text="Remove favorite" if cur and cur in self.favorites() else "Add to favorites",
                               state="normal" if cur else "disabled")
        self.refresh_favorites()
        if self.brush is None:
            self.brush_var.set("Brush: plain digging")
        else:
            self.brush_var.set("Brush: dig, then place %s (slot %d)" % (item_label(d.inv[self.brush]), self.brush))
        lines = []
        for s in sorted(d.inv):
            n = need.get(s, 0)
            extra = ""
            if n > 64:
                extra = "  (more than a stack: put %d in, I'll wait for a refill)" % 64
            lines.append("Slot %d  %s: %d to place%s" % (s, item_label(d.inv[s]), n, extra))
        if not lines:
            lines.append("No items assigned. The turtle only digs.")
        else:
            lines.append("Load these onto the turtle before it starts.")
        self.supply_var.set("\n".join(lines))

    def sync_options(self):
        self.pattern_var.set(dict(PATTERNS).get(self.design.pattern, PATTERNS[0][1]))
        self.torch_mode_var.set(dict(TORCH_MODES).get(self.design.torch_mode, TORCH_MODES[0][1]))

    def pick_pattern(self):
        if self.mode != "edit":
            self.sync_options()
            return
        key = next((k for k, label in PATTERNS if label == self.pattern_var.get()), None)
        if key and key != self.design.pattern:
            self.snapshot()
            self.design.pattern = key
            self.after_edit()

    def pick_torch_mode(self):
        if self.mode != "edit":
            self.sync_options()
            return
        key = next((k for k, label in TORCH_MODES if label == self.torch_mode_var.get()), None)
        if key and key != self.design.torch_mode:
            self.snapshot()
            self.design.torch_mode = key
            self.after_edit()

    # ------------------------------------------------------------------ interaction
    def inv_slot_at(self, e):
        px = self.SLOT_PX
        col, row = int(e.x // px), int(e.y // px)
        if 0 <= col < 4 and 0 <= row < 4:
            return row * 4 + col + 1
        return None

    def inv_click(self, e):
        s = self.inv_slot_at(e)
        if s is not None:
            self.sel_slot = s
            self.refresh_inventory()

    def inv_double(self, e):
        s = self.inv_slot_at(e)
        if s is not None:
            self.sel_slot = s
            self.use_brush()

    def set_slot_from_box(self):
        if self.mode != "edit":
            return
        name = clean_item(self.item_var.get())
        if name is None:
            self.error("Item", "That doesn't look like an item id.\nUse something like  minecraft:cobblestone  or  torch.")
            return
        self.assign_item(name)

    def assign_item(self, name, slot=None):
        """Put `name` into a turtle slot (the selected one by default). True when it worked."""
        if self.mode != "edit":
            return False
        d = self.design
        s = slot or self.sel_slot
        if d.inv.get(s) == name:
            return True
        if s not in d.inv and len(d.inv) >= MAX_SUPPLY_SLOTS:
            self.error("Item", "At most %d slots can be reserved - the turtle needs the others for "
                               "what it digs up." % MAX_SUPPLY_SLOTS)
            return False
        self.snapshot()
        d.set_slot_item(s, name)
        self.after_edit()
        return True

    # ------------------------------------------------------------------ favorites
    def favorites(self):
        favs = self.cfg.get("favorites")
        if not isinstance(favs, list):
            favs = list(DEFAULT_FAVORITES)
        return [f for f in favs if isinstance(f, str)]

    def set_favorite(self, name, on):
        favs = [f for f in self.favorites() if f != name]
        if on:
            favs.append(name)
        self.cfg["favorites"] = favs
        save_config(self.cfg)
        self.refresh_favorites()
        cur = self.design.inv.get(self.sel_slot)
        self.fav_btn.configure(text="Remove favorite" if cur and cur in favs else "Add to favorites")

    def toggle_slot_favorite(self):
        cur = self.design.inv.get(self.sel_slot)
        if cur:
            self.set_favorite(cur, cur not in self.favorites())

    def refresh_favorites(self):
        bar = getattr(self, "fav_bar", None)
        if bar is None:
            return
        for w in bar.winfo_children():
            w.destroy()
        favs = self.favorites()
        bank = self.icon_bank()
        self.fav_title.configure(text="Favorites (click to put one in slot %d)" % self.sel_slot)
        if not favs:
            ttk.Label(bar, foreground="#666", text="None yet - use 'Add to favorites' or Browse items.").pack(anchor="w")
        for i, name in enumerate(favs[:16]):
            img = bank.picture(name, 2) if bank else None
            b = tk.Button(bar, image=img, width=36, height=36, relief="groove", borderwidth=2,
                          command=lambda n=name: self.assign_item(n)) if img is not None else \
                tk.Button(bar, text=item_label(name)[:3], width=3, height=2, bg=item_color(name),
                          command=lambda n=name: self.assign_item(n))
            b.grid(row=i // 8, column=i % 8, padx=1, pady=1)
            b.bind("<Enter>", lambda e, n=name: self.fav_hint.set(item_label(n)))
            b.bind("<Leave>", lambda e: self.fav_hint.set(""))

    # ------------------------------------------------------------------ item picker window
    def open_picker(self, callback=None):
        """Browse items. With a callback, a chosen item is handed to it instead of going into a turtle slot."""
        self.pick_cb = callback
        win = getattr(self, "picker", None)
        if win is not None and win.winfo_exists():
            win.lift()
            self.picker_fill()
            return
        win = self.picker = tk.Toplevel(self.root)
        win.title("Choose an item")
        win.geometry("430x580")
        win.transient(self.root)
        top = ttk.Frame(win, padding=(8, 8, 8, 0))
        top.pack(fill="x")
        ttk.Label(top, text="Search").pack(side="left")
        self.pick_q = tk.StringVar()
        ent = ttk.Entry(top, textvariable=self.pick_q)
        ent.pack(side="left", fill="x", expand=True, padx=6)
        self.pick_q.trace_add("write", lambda *a: self.picker_fill())
        self.pick_favs_only = tk.BooleanVar(value=False)
        ttk.Checkbutton(top, text="Favorites only", variable=self.pick_favs_only,
                        command=self.picker_fill).pack(side="left")
        ttk.Label(win, foreground="#666", wraplength=400, justify="left", padding=(8, 2), text=(
            "Double-click an item to put it in the selected slot. Click the box in the Favorite column to star it. "
            "Items from mods: type their full id (like  mymod:cool_block)  and double-click the row that appears."
        )).pack(fill="x")
        style = ttk.Style(win)
        style.configure("Pick.Treeview", rowheight=26)
        mid = ttk.Frame(win, padding=8)
        mid.pack(fill="both", expand=True)
        self.pick_tree = tv = ttk.Treeview(mid, columns=("fav",), style="Pick.Treeview", selectmode="browse")
        tv.heading("#0", text="Item")
        tv.heading("fav", text="Favorite")
        tv.column("#0", width=280)
        tv.column("fav", width=70, anchor="center", stretch=False)
        sb = ttk.Scrollbar(mid, orient="vertical", command=tv.yview)
        tv.configure(yscrollcommand=sb.set)
        tv.pack(side="left", fill="both", expand=True)
        sb.pack(side="left", fill="y")
        tv.bind("<Double-1>", self.picker_double)
        tv.bind("<ButtonRelease-1>", self.picker_click)
        tv.bind("<Return>", lambda e: self.picker_use())
        bot = ttk.Frame(win, padding=(8, 0, 8, 8))
        bot.pack(fill="x")
        self.pick_info = tk.StringVar()
        ttk.Label(bot, textvariable=self.pick_info, foreground="#666").pack(anchor="w")
        row = ttk.Frame(bot)
        row.pack(fill="x", pady=(4, 0))
        self.pick_use_btn = ttk.Button(row, text="Put in slot", command=self.picker_use)
        self.pick_use_btn.pack(side="left")
        ttk.Button(row, text="Add / remove favorite", command=self.picker_toggle).pack(side="left", padx=4)
        ttk.Button(row, text="Close", command=win.destroy).pack(side="right")
        self.picker_fill()
        ent.focus_set()

    def picker_names(self):
        q = self.pick_q.get().strip().lower().replace(" ", "_")
        favs = self.favorites()
        bank = self.icon_bank()
        pool = [f for f in favs]
        if not self.pick_favs_only.get():
            seen = set(pool)
            for n in [n for n, _c in ITEM_PRESETS] + (bank.names() if bank else []):
                if n not in seen:
                    seen.add(n)
                    pool.append(n)
        out = [n for n in pool if q in n.lower()] if q else pool
        typed = clean_item(q) if q and ":" in q else None
        if typed and typed not in out:
            out.insert(0, typed)
        return out

    def picker_fill(self):
        tv = getattr(self, "pick_tree", None)
        if tv is None or not tv.winfo_exists():
            return
        names = self.picker_names()
        favs = set(self.favorites())
        bank = self.icon_bank()
        tv.delete(*tv.get_children())
        for n in names[:300]:
            img = bank.picture(n, 1) if bank else ""
            tv.insert("", "end", iid=n, text="  " + item_label(n) + ("" if n.startswith("minecraft:") else "   (" + n + ")"),
                      image=img or "", values=("[x]" if n in favs else "[ ]",))
        extra = len(names) - 300
        self.pick_info.set("%d items%s" % (len(names), "  (showing the first 300 - type to narrow)" if extra > 0 else ""))
        self.pick_use_btn.configure(text="Choose" if getattr(self, "pick_cb", None) else "Put in slot %d" % self.sel_slot)

    def picker_selected(self):
        sel = self.pick_tree.selection()
        return sel[0] if sel else None

    def picker_click(self, e):
        tv = self.pick_tree
        if tv.identify_region(e.x, e.y) == "cell" and tv.identify_column(e.x) == "#1":
            row = tv.identify_row(e.y)
            if row:
                self.set_favorite(row, row not in self.favorites())
                keep = tv.yview()
                self.picker_fill()
                tv.yview_moveto(keep[0])
                if tv.exists(row):
                    tv.selection_set(row)

    def picker_double(self, e):
        tv = self.pick_tree
        if tv.identify_region(e.x, e.y) == "tree" or tv.identify_column(e.x) == "#0":
            self.picker_use()

    def picker_use(self):
        n = self.picker_selected()
        cb = getattr(self, "pick_cb", None)
        if n and cb:
            self.picker.destroy()
            self.pick_cb = None
            cb(n)
        elif n and self.assign_item(n):
            self.picker.destroy()

    def picker_toggle(self):
        n = self.picker_selected()
        if n:
            self.set_favorite(n, n not in self.favorites())
            self.picker_fill()
            if self.pick_tree.exists(n):
                self.pick_tree.selection_set(n)

    def empty_slot(self):
        if self.mode != "edit" or self.sel_slot not in self.design.inv:
            return
        self.snapshot()
        self.design.set_slot_item(self.sel_slot, None)
        self.after_edit()

    def use_brush(self):
        if self.sel_slot not in self.design.inv:
            self.info("Brush", "Put an item in slot %d first." % self.sel_slot)
            return
        self.brush = self.sel_slot
        if self.tool.get() == "turtle":
            self.tool.set("pencil")
        self.refresh_inventory()
        self.refresh_layer()

    def dig_only(self):
        self.brush = None
        self.refresh_inventory()

    def add_torches(self):
        if self.mode != "edit":
            return
        d = self.design
        slot = next((s for s, n in sorted(d.inv.items()) if n == TORCH), None)
        if slot is None:
            free = [s for s in range(16, 0, -1) if s not in d.inv]
            if len(d.inv) >= MAX_SUPPLY_SLOTS or not free:
                self.error("Torches", "No slot left to hold torches.")
                return
            slot = free[0]
        try:
            gap = int(self.torch_gap.get())
        except (tk.TclError, ValueError):
            self.error("Torches", "Enter a whole number for the spacing.")
            return
        self.snapshot()
        had = slot in d.inv
        d.inv[slot] = TORCH
        added = auto_torches(d, gap, slot)
        if added == 0:
            self.undo.pop()
            if not had:
                del d.inv[slot]
            self.info("Torches", "No spot found. A torch is dropped onto the floor from the cell above, so it needs a dug cell above it (the design must be at least 2 layers tall) and a solid floor below.")
            return
        self.sel_slot = slot
        self.after_edit()

    def clear_all_blocks(self):
        if self.mode != "edit" or not self.design.place:
            return
        self.snapshot()
        clear_blocks(self.design)
        self.after_edit()

    # ------------------------------------------------------------------ textures: built-in or your own
    def texture_status(self):
        n = len(TEX["tiles"])
        if not n:
            return "Built-in simplified textures. Nothing imported yet."
        return "%d imported textures from: %s" % (n, ", ".join(TEX["sources"]) or "?")

    def set_texture_mode(self, mode):
        if mode == "imported" and not TEX["tiles"]:
            mode = "builtin"
        TEX["mode"] = mode
        self.cfg["texture_mode"] = mode
        save_config(self.cfg)
        bank = self.icon_bank()
        if bank:
            bank.cache.clear()
        self.mcache = {}
        self.refresh_inventory()
        self.relayout(force=True)
        if getattr(self, "picker", None) is not None and self.picker.winfo_exists():
            self.picker_fill()
        if hasattr(self, "tex_mode_var"):
            self.tex_mode_var.set(mode)
            self.tex_status.set(self.texture_status())

    def import_textures(self, paths=None):
        if paths is None:
            paths = filedialog.askopenfilenames(
                title="Choose a resource pack, a Minecraft version .jar, or a mod .jar",
                filetypes=[("Resource pack / jar", "*.zip *.jar"), ("All files", "*.*")])
        total = 0
        for path in paths or ():
            try:
                total += import_texture_file(self.root, path)
            except ValueError as ex:
                self.error("Textures", "%s\n\n%s" % (os.path.basename(path), ex))
        if total:
            self.set_texture_mode("imported")
        return total

    def remove_textures(self):
        clear_texpack()
        self.set_texture_mode("builtin")

    def open_textures(self):
        win = getattr(self, "tex_win", None)
        if win is not None and win.winfo_exists():
            win.lift()
            return
        win = self.tex_win = tk.Toplevel(self.root)
        win.title("Textures")
        win.transient(self.root)
        f = ttk.Frame(win, padding=12)
        f.pack(fill="both", expand=True)
        bold = ("TkDefaultFont", 10, "bold")
        ttk.Label(f, text="Item pictures", font=bold).pack(anchor="w")
        self.tex_mode_var = tk.StringVar(value=TEX["mode"])
        ttk.Radiobutton(f, text="Built-in simplified textures (colour-matched to Minecraft)", value="builtin",
                        variable=self.tex_mode_var, command=lambda: self.set_texture_mode("builtin")).pack(anchor="w", pady=(4, 0))
        ttk.Radiobutton(f, text="My imported textures", value="imported", variable=self.tex_mode_var,
                        command=lambda: self.set_texture_mode("imported")).pack(anchor="w")
        self.tex_status = tk.StringVar(value=self.texture_status())
        ttk.Label(f, textvariable=self.tex_status, wraplength=380, justify="left", foreground="#555").pack(anchor="w", pady=(6, 6))
        row = ttk.Frame(f)
        row.pack(fill="x")
        ttk.Button(row, text="Import resource pack / jar...", command=self.import_textures).pack(side="left")
        ttk.Button(row, text="Remove imported", command=self.remove_textures).pack(side="left", padx=6)
        ttk.Label(f, wraplength=380, justify="left", foreground="#666", text=(
            "Pick a resource pack (.zip), Minecraft's own version file (in your .minecraft/versions folder, "
            "e.g. 1.21.1/1.21.1.jar) or a mod's .jar. Items from mods get their pictures too. "
            "Everything stays on your computer. The 3D pages you export carry only the few textures they use.")
                  ).pack(anchor="w", pady=(10, 0))
        ttk.Button(f, text="Close", command=win.destroy).pack(anchor="e", pady=(10, 0))
# GUI part: the Automation tab (tree farm, smelter, crafter ... settings and the text pictures of their layouts).
# ================================================================ GUI: Automation tab
def auto_diagram(p):
    """A small text picture of how a job is laid out."""
    p = clean_auto(p)
    if p["kind"] == "treefarm":
        cols, rows, S = min(p["cols"], 6), min(p["rows"], 4), min(p["spacing"], 5)
        out = []
        for j in range(rows):
            lane = "+" + "".join((("-" * (S - 1)) + "o") for _ in range(cols))      # o = where it stands
            tree = " " + "".join((" " * (S - 1)) + "T" for _ in range(cols))
            out.append(lane + ("  ..." if p["cols"] > cols else ""))
            out.append(tree)
            if j < rows - 1:
                out.append("|")
        if p["rows"] > rows:
            out.append("... (%d rows)" % p["rows"])
        out.append("")
        out.append("+ = the START column (walkway, keep it free), o = where it stands, T = a tree")
        out.append("[chest] directly behind the START (below the first +)" if p["chest"] else "no chest")
        return "\n".join(out)
    if p["kind"] == "smelter":
        n = min(p["furnaces"], 10)
        return "\n".join([
            "  " + " ".join("F" for _ in range(n)) + ("  ..." if p["furnaces"] > n else "") + "     F = furnace (%d), free air above and below" % p["furnaces"],
            "  " + " ".join("-" for _ in range(n)) + "     the turtle's walkway",
            "[out] S             S = START, [out] = result chest on its left",
            "      [in]          [in] = chest behind it: raw items + %s" % item_label(p["fuel"]).lower(),
        ])
    if p["kind"] == "hauler":
        rows = []
        for l in p["legs"]:
            rows.append("[%s out] --%s--> [%s in]" % (l["from"], l["item"] or "everything", l["to"]))
        return "\n".join(rows + ["", "It stands on top of each chest, takes from the first and drops into the second."])
    if p["kind"] == "keeper":
        return "\n".join([
            "      [above]", "[left] <- corridor -> [right]   x %d steps, 4 storage chests per step" % p["length"], "      [below]", "",
            "[pickup]  S  ---> corridor ...      [pickup] = chest left of the start: what you ask for",
            "        [drop]                      [drop]   = chest behind it: put things in here"])
    if p["kind"] == "miner":
        return "\n".join([
            "  S  <- start (chest behind it)", "  |", "  |  shaft %d down" % p["depth"], "  |",
            "  +----+----+----+----> main tunnel %d long" % p["reach"],
            "       |    |    |", "       |    |    |   side tunnels (%d long) every 3 blocks, both sides" % p["rib"],
            "", "It scans every wall and mines any wanted ore it sees."])
    if p["kind"] == "scout":
        return "\n".join([
            "      ^ up %d" % p["up"], "      |", "  <---+--->   +/- %d blocks each way (S = start)" % p["radius"], "      |",
            "      v down %d" % p["down"], "",
            "It walks and flies through open space, looking at every side,",
            "and the blocks it sees appear on the Fleet map."])
    if p["kind"] == "agent":
        return "\n".join(["  [ idle ]  --- order from the Fleet tab or another turtle --->  [ runs carve <program> ]",
                           "", "When the program ends it goes back to waiting."])
    cells = [(item_label(g) if g else "-")[:11] for g in p["grid"]]
    rows = ["| " + " | ".join(c.ljust(11) for c in cells[i:i + 3]) + " |" for i in (0, 3, 6)]
    return "\n".join(rows + ["", "[in] chest behind the START: ingredients      [out] chest on its left: results"])


class AutoMixin:
    """The Automation tab: ready-made tree farm, auto smelter and auto crafter programs."""

    def build_auto_tab(self, f):
        bold = ("TkDefaultFont", 10, "bold")
        self.auto_kind = tk.StringVar(value="Tree farm")
        self.auto_name = tk.StringVar(value="Tree farm")
        self.auto_vars = {
            "cols": tk.StringVar(value="3"), "rows": tk.StringVar(value="3"), "spacing": tk.StringVar(value="4"),
            "sapling": tk.StringVar(value="Oak"), "bonemeal": tk.BooleanVar(value=False), "wait": tk.StringVar(value="600"),
            "cycles": tk.StringVar(value="0"), "chest": tk.BooleanVar(value=True),
            "furnaces": tk.StringVar(value="4"), "once": tk.BooleanVar(value=False),
            "total": tk.StringVar(value="0"),
            "hwait": tk.StringVar(value="20"),
            "klen": tk.StringVar(value="8"), "kwait": tk.StringVar(value="10"), "krescan": tk.StringVar(value="1800"),
            "depth": tk.StringVar(value="20"), "reach": tk.StringVar(value="30"), "rib": tk.StringVar(value="12"),
            "radius": tk.StringVar(value="24"), "up": tk.StringVar(value="8"), "down": tk.StringVar(value="4"),
        }
        self.auto_legs = [{k: tk.StringVar() for k in ("from", "to", "item")} for _ in range(4)]
        self.auto_want = {k: tk.BooleanVar(value=True) for k, _l in MINER_RESOURCES}
        self.auto_fuel = "minecraft:coal"
        self.auto_grid = [None] * 9
        self.auto_out = ""
        ttk.Label(f, text="Automation", font=bold).pack(anchor="w")
        ttk.Label(f, foreground="#555", wraplength=330, justify="left", text=(
            "Ready-made turtle programs that keep working: a tree farm, an auto smelter and an auto crafter. "
            "Set them up here, upload them like a design, then run  carve <name>  on the turtle.")).pack(anchor="w", pady=(0, 4))
        row = ttk.Frame(f)
        row.pack(fill="x")
        ttk.Label(row, text="Type").pack(side="left")
        box = ttk.Combobox(row, textvariable=self.auto_kind, state="readonly", width=16, values=[l for _k, l in AUTO_KINDS])
        box.pack(side="left", padx=4)
        box.bind("<<ComboboxSelected>>", lambda e: self.auto_switch())
        ttk.Label(row, text="Name").pack(side="left", padx=(8, 0))
        ttk.Entry(row, textvariable=self.auto_name, width=16).pack(side="left", padx=4)
        self.auto_body = ttk.Frame(f)
        self.auto_body.pack(fill="x", pady=6)
        self.auto_text = tk.Text(f, height=15, width=48, wrap="word", font=("TkFixedFont", 9))
        self.auto_text.pack(fill="both", expand=True)
        row = ttk.Frame(f)
        row.pack(fill="x", pady=(6, 0))
        ttk.Button(row, text="Upload to GitHub", command=self.auto_upload).pack(side="left", fill="x", expand=True)
        ttk.Button(row, text="Save .lua file...", command=self.auto_save_lua).pack(side="left", fill="x", expand=True, padx=(4, 0))
        self.auto_status = tk.StringVar(value="")
        ttk.Label(f, textvariable=self.auto_status, wraplength=330, justify="left").pack(anchor="w", pady=(4, 0))
        self.auto_switch()

    def show_tab(self, title):
        try:
            self.nb.select(self.tabs[title])
        except (KeyError, tk.TclError):
            pass

    def auto_kind_key(self):
        return {l: k for k, l in AUTO_KINDS}.get(self.auto_kind.get(), "treefarm")

    def auto_switch(self):
        kind = self.auto_kind_key()
        default = auto_default(kind)
        if self.auto_name.get() in {auto_default(k)["name"] for k, _l in AUTO_KINDS} or not self.auto_name.get().strip():
            self.auto_name.set(default["name"])
        for w in self.auto_body.winfo_children():
            w.destroy()
        b, v = self.auto_body, self.auto_vars

        def spin(parent, label, var, lo, hi, width=5):
            r = ttk.Frame(parent)
            r.pack(fill="x", pady=1)
            ttk.Label(r, text=label, width=24).pack(side="left")
            ttk.Spinbox(r, from_=lo, to=hi, width=width, textvariable=var, command=self.auto_refresh).pack(side="left")
            var.trace_add("write", lambda *a: self.auto_refresh())

        def check(parent, label, var):
            ttk.Checkbutton(parent, text=label, variable=var, command=self.auto_refresh).pack(anchor="w")
        if kind == "treefarm":
            spin(b, "Trees per row", v["cols"], 1, 12)
            spin(b, "Rows", v["rows"], 1, 12)
            spin(b, "Space between trees", v["spacing"], 3, 8)
            r = ttk.Frame(b)
            r.pack(fill="x", pady=1)
            ttk.Label(r, text="Sapling", width=24).pack(side="left")
            sb = ttk.Combobox(r, textvariable=v["sapling"], state="readonly", width=18, values=[l for _k, l in SAPLINGS])
            sb.pack(side="left")
            sb.bind("<<ComboboxSelected>>", lambda e: self.auto_refresh())
            check(b, "Use bone meal (slot 2) - trees grow at once", v["bonemeal"])
            spin(b, "Wait between rounds (s)", v["wait"], 30, 7200)
            spin(b, "Rounds (0 = forever)", v["cycles"], 0, 999)
            check(b, "Chest directly behind the start", v["chest"])
        elif kind == "smelter":
            spin(b, "Furnaces", v["furnaces"], 1, 16)
            r = ttk.Frame(b)
            r.pack(fill="x", pady=1)
            ttk.Label(r, text="Fuel", width=24).pack(side="left")
            self.auto_fuel_btn = ttk.Button(r, text=item_label(self.auto_fuel), command=self.auto_pick_fuel)
            self.auto_fuel_btn.pack(side="left")
            check(b, "Stop when the input chest is empty", v["once"])
        elif kind == "hauler":
            ttk.Label(b, foreground="#555", wraplength=330, justify="left", text=(
                "Each leg: take from the OUTPUT chest of one job, put in the INPUT chest of another. Use the job's name. "
                "Item filter = part of an item name (log, charcoal); empty = everything.")).pack(anchor="w")
            names = lambda: self.fleet.stations() if hasattr(self, "fleet") else []
            for i, leg in enumerate(self.auto_legs):
                r = ttk.Frame(b)
                r.pack(fill="x", pady=1)
                ttk.Label(r, text="%d" % (i + 1), width=2).pack(side="left")
                for key, w in (("from", 14), ("to", 14)):
                    ttk.Combobox(r, textvariable=leg[key], width=w, postcommand=lambda: None).pack(side="left", padx=1)
                    leg[key].trace_add("write", lambda *a: self.auto_refresh())
                    if key == "from":
                        ttk.Label(r, text="->").pack(side="left")
                ttk.Entry(r, textvariable=leg["item"], width=9).pack(side="left", padx=(3, 0))
                leg["item"].trace_add("write", lambda *a: self.auto_refresh())
            for w in b.winfo_children():
                for c in w.winfo_children():
                    if isinstance(c, ttk.Combobox):
                        c.configure(postcommand=lambda c=c: c.configure(values=names()))
            ttk.Label(b, foreground="#666", text="Columns: take from  ->  put in   |  item filter").pack(anchor="w")
            spin(b, "Wait when idle (s)", v["hwait"], 5, 600)
            spin(b, "Rounds (0 = forever)", v["cycles"], 0, 9999)
        elif kind == "keeper":
            ttk.Label(b, foreground="#555", wraplength=330, justify="left", text=(
                "Give it a chest in the first slot (and more chests plus fuel in other slots) and start it: it places a DROP chest behind it, "
                "a PICKUP chest on its left, and builds storage chests along a corridor as it needs room. See and order items on the Fleet page, Storage tab.")).pack(anchor="w")
            spin(b, "Corridor length (steps)", v["klen"], 1, 30)
            spin(b, "Wait between checks (s)", v["kwait"], 3, 300)
            spin(b, "Re-count chests every (s)", v["krescan"], 0, 86400)
        elif kind == "miner":
            spin(b, "Shaft depth (blocks)", v["depth"], 4, 120)
            spin(b, "Main tunnel length", v["reach"], 3, 96)
            spin(b, "Side tunnel length", v["rib"], 0, 32)
            ttk.Label(b, text="Look for").pack(anchor="w")
            row = ttk.Frame(b)
            row.pack(anchor="w")
            for i, (k, label) in enumerate(MINER_RESOURCES):
                ttk.Checkbutton(row, text=label, variable=self.auto_want[k], command=self.auto_refresh).grid(row=i // 4, column=i % 4, sticky="w")
        elif kind == "scout":
            spin(b, "Radius (blocks)", v["radius"], 4, 64)
            spin(b, "Up from the start", v["up"], 0, 40)
            spin(b, "Down from the start", v["down"], 0, 40)
        elif kind == "agent":
            ttk.Label(b, foreground="#555", wraplength=330, justify="left",
                      text="Nothing to set. Name it, upload it, and it waits for orders.").pack(anchor="w")
        else:
            g = ttk.Frame(b)
            g.pack(anchor="w")
            self.auto_cells = []
            for i in range(9):
                btn = ttk.Button(g, text="-", width=13, command=lambda i=i: self.auto_pick_cell(i))
                btn.grid(row=i // 3, column=i % 3, padx=1, pady=1)
                btn.bind("<Button-3>", lambda e, i=i: self.auto_set_cell(i, None))
                self.auto_cells.append(btn)
            ttk.Label(b, foreground="#666", text="Click a cell to pick its item, right-click to empty it.").pack(anchor="w")
            ttk.Button(b, text="Preset: charcoal blocks (9 charcoal)", command=self.auto_preset_charcoal).pack(anchor="w", pady=2)
            spin(b, "Crafts (0 = until out)", v["total"], 0, 99999)
            check(b, "Stop when the input chest is empty", v["once"])
            self.auto_cells_refresh()
        self.auto_refresh()

    def auto_cells_refresh(self):
        for i, btn in enumerate(getattr(self, "auto_cells", [])):
            try:
                btn.configure(text=item_label(self.auto_grid[i])[:13] if self.auto_grid[i] else "-")
            except tk.TclError:
                pass

    def auto_preset_charcoal(self):
        """Nine charcoal in the grid: the crafter condenses it into charcoal blocks (a modded item; vanilla has none)."""
        self.auto_grid = ["minecraft:charcoal"] * 9
        if self.auto_name.get() in ("Auto crafter", ""):
            self.auto_name.set("Charcoal compressor")
        self.auto_cells_refresh()
        self.auto_refresh()

    def auto_set_cell(self, i, item):
        self.auto_grid[i] = item
        self.auto_cells_refresh()
        self.auto_refresh()

    def auto_pick_cell(self, i):
        self.open_picker(lambda name: self.auto_set_cell(i, name))

    def auto_pick_fuel(self):
        def got(name):
            self.auto_fuel = name
            try:
                self.auto_fuel_btn.configure(text=item_label(name))
            except tk.TclError:
                pass
            self.auto_refresh()
        self.open_picker(got)

    def auto_job(self):
        """The settings on screen as a job dict (not yet validated)."""
        kind, v = self.auto_kind_key(), self.auto_vars
        job = {"kind": kind, "name": self.auto_name.get()}
        saps = {l: k for k, l in SAPLINGS}
        if kind == "treefarm":
            job.update(cols=v["cols"].get(), rows=v["rows"].get(), spacing=v["spacing"].get(),
                       sapling=saps.get(v["sapling"].get(), "minecraft:oak_sapling"), bonemeal=v["bonemeal"].get(),
                       wait=v["wait"].get(), cycles=v["cycles"].get(), chest=v["chest"].get())
        elif kind == "smelter":
            job.update(furnaces=v["furnaces"].get(), fuel=self.auto_fuel, once=v["once"].get())
        elif kind == "hauler":
            job.update(legs=[{k: v.get() for k, v in leg.items()} for leg in self.auto_legs], wait=v["hwait"].get(), cycles=v["cycles"].get())
        elif kind == "keeper":
            job.update(length=v["klen"].get(), wait=v["kwait"].get(), rescan=v["krescan"].get())
        elif kind == "miner":
            job.update(depth=v["depth"].get(), reach=v["reach"].get(), rib=v["rib"].get(),
                       want=[k for k, _l in MINER_RESOURCES if self.auto_want[k].get()])
        elif kind == "scout":
            job.update(radius=v["radius"].get(), up=v["up"].get(), down=v["down"].get())
        elif kind == "agent":
            pass
        else:
            job.update(grid=list(self.auto_grid), total=v["total"].get(), once=v["once"].get())
        return job

    def auto_load(self, job):
        """Show a saved job on screen."""
        job = clean_auto(job)
        self.auto_kind.set(dict(AUTO_KINDS)[job["kind"]])
        self.auto_name.set(job["name"])
        self.auto_switch()
        v = self.auto_vars
        if job["kind"] == "treefarm":
            for k in ("cols", "rows", "spacing", "wait", "cycles"):
                v[k].set(str(job[k]))
            v["sapling"].set(dict(SAPLINGS).get(job["sapling"], job["sapling"]))
            v["bonemeal"].set(job["bonemeal"])
            v["chest"].set(job["chest"])
        elif job["kind"] == "hauler":
            for leg, src in zip(self.auto_legs, job["legs"] + [{}] * 4):
                for k, var in leg.items():
                    var.set(src.get(k, ""))
            v["hwait"].set(str(job["wait"]))
            v["cycles"].set(str(job["cycles"]))
        elif job["kind"] == "keeper":
            v["klen"].set(str(job["length"]))
            v["kwait"].set(str(job["wait"]))
            v["krescan"].set(str(job["rescan"]))
        elif job["kind"] == "miner":
            for k in ("depth", "reach", "rib"):
                v[k].set(str(job[k]))
            for k, var in self.auto_want.items():
                var.set(k in job["want"])
        elif job["kind"] == "scout":
            for k in ("radius", "up", "down"):
                v[k].set(str(job[k]))
        elif job["kind"] == "agent":
            pass
        elif job["kind"] == "smelter":
            v["furnaces"].set(str(job["furnaces"]))
            self.auto_fuel = job["fuel"]
            self.auto_fuel_btn.configure(text=item_label(job["fuel"]))
            v["once"].set(job["once"])
        else:
            self.auto_grid = list(job["grid"])
            v["total"].set(str(job["total"]))
            v["once"].set(job["once"])
            self.auto_cells_refresh()
        self.auto_refresh()

    def auto_refresh(self):
        if not hasattr(self, "auto_text"):
            return
        try:
            job = clean_auto(self.auto_job())
            text = auto_diagram(job) + "\n\n" + "\n".join(auto_summary(job)["lines"])
            warns = auto_summary(job)["warnings"]
            if warns:
                text += "\n\nHeads up:\n" + "\n".join("- " + w for w in warns)
            self.auto_ok = True
        except (ValueError, tk.TclError) as ex:
            text = "Check the settings: %s" % ex
            self.auto_ok = False
        self.auto_text.configure(state="normal")
        self.auto_text.delete("1.0", "end")
        self.auto_text.insert("1.0", text)
        self.auto_text.configure(state="disabled")

    def auto_valid_job(self):
        try:
            return clean_auto(self.auto_job())
        except (ValueError, tk.TclError) as ex:
            self.auto_status.set("Check the settings: %s" % ex)
            return None

    def auto_save_lua(self):
        job = self.auto_valid_job()
        if not job:
            return
        path = self.ask_save_path(defaultextension=".lua", initialfile=auto_slug(job) + ".lua", filetypes=[("Lua program", "*.lua")])
        if not path:
            return
        with open(path, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(generate_auto_lua(job))
        self.auto_status.set("Saved %s. Copy it to the turtle and run it." % path)

    def auto_upload(self):
        job = self.auto_valid_job()
        if not job:
            return
        cfg = self.collect_github_cfg()
        if cfg is None:
            self.auto_status.set(self.gh_status.get() or "Fill in the GitHub tab first.")
            return
        self.auto_status.set("Uploading...")

        def done(info):
            self.last_upload = info
            menu, prog = turtle_commands(info)
            self.refresh_turtle_commands()
            self.cmd2_var.set("carve %s" % info["slug"])
            self.root.clipboard_clear()
            self.root.clipboard_append(menu)
            extra = {"smelter": "  First run  carve %s setup  with the furnaces in the turtle." % info["slug"],
                     "miner": "  Chest behind the start, coal in the turtle.",
                     "keeper": "  A chest in the first slot, more chests and fuel in other slots. Items: Fleet page, Storage tab.",
                     "scout": "  Needs live reporting for the map, and a start position (Fleet tab).",
                     "agent": "  Start it once; then start jobs on it from the Fleet tab."}.get(info["kind"], "")
            self.auto_status.set("Uploaded \"%s\". On the turtle: carve %s.%s  The install command is copied." % (
                info["name"], info["slug"], extra))
        live_url = self.live_url_for_upload()
        if live_url is None:
            self.auto_status.set(self.gh_status.get())
            return
        self.run_bg(lambda: publish_auto(cfg, job, live_url), done, lambda ex: self.auto_status.set(str(ex)))
# GUI part: the Fleet / Colony tab - turtle list, start the server, upload colony programs, lay out and send jobs.
# v7.9: 'Lay out' checks the typed start cell against the Foreman's position (a stale coordinate sent turtles hundreds of blocks away).
# ================================================================ GUI: Fleet tab
def lan_address():
    """This computer's address on the local network (best guess), or ''."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))
        return s.getsockname()[0]
    except OSError:
        return ""
    finally:
        s.close()


class FleetMixin:
    """The Fleet tab: every turtle that reports in, at a glance, with a Stop button."""
    FLEET_COLS = (("name", "Turtle", 150), ("job", "Job", 80), ("state", "State", 100), ("progress", "Progress", 80),
                  ("fuel", "Fuel", 60), ("pos", "Where", 120), ("seen", "Seen", 70), ("msg", "Message", 260))

    def build_fleet_tab(self, f):
        self.fleet = Fleet()
        self.fleet_job = None
        for tid, a in (self.cfg.get("anchors") or {}).items():          # start positions typed in earlier
            try:
                self.fleet.typed[int(tid)] = (int(a[0]), int(a[1]), int(a[2]), a[3] if a[3] in FACINGS else "north")
            except (TypeError, ValueError, IndexError):
                pass
        for tid, g in (self.cfg.get("gods") or {}).items():             # names given from the Roman gods list
            if isinstance(g, str) and str(tid).isdigit():
                self.fleet.gods[int(tid)] = g[:30]
        self.fleet.on_anchor = self.fleet_save_anchors
        bold = ("TkDefaultFont", 10, "bold")
        ttk.Label(f, text="Fleet", font=bold).pack(anchor="w")
        ttk.Label(f, foreground="#555", wraplength=330, justify="left", text=(
            "See every turtle at once: what it is doing, its fuel and place, and any problem. Programs uploaded "
            "with live reporting send a report every few seconds. Press Start listening, then open the page below "
            "(it works in any browser, also on a phone on the same network).")).pack(anchor="w", pady=(0, 4))
        row = ttk.Frame(f)
        row.pack(fill="x")
        self.fleet_btn = ttk.Button(row, text="Start listening", command=self.fleet_toggle)
        self.fleet_btn.pack(side="left")
        ttk.Button(row, text="Open the Fleet page", command=self.fleet_open_page).pack(side="left", padx=4)
        ttk.Button(row, text="Copy address", command=self.fleet_copy_address).pack(side="left")
        self.fleet_info = tk.StringVar(value="Not listening.")
        ttk.Label(f, textvariable=self.fleet_info, wraplength=330, justify="left", foreground="#333").pack(anchor="w", pady=2)
        cols = [c[0] for c in self.FLEET_COLS]
        self.fleet_tree = ttk.Treeview(f, columns=cols, show="headings", height=8, selectmode="browse")
        for key, title, w in self.FLEET_COLS:
            self.fleet_tree.heading(key, text=title)
            self.fleet_tree.column(key, width=w, minwidth=40, stretch=(key == "msg"))
        self.fleet_tree.pack(fill="both", expand=True, pady=4)
        row = ttk.Frame(f)
        row.pack(fill="x")
        ttk.Button(row, text="Stop selected", command=self.fleet_stop).pack(side="left")
        ttk.Button(row, text="Start program...", command=self.fleet_run_dialog).pack(side="left", padx=4)
        ttk.Button(row, text="Forget selected", command=self.fleet_forget).pack(side="left")
        row = ttk.Frame(f)
        row.pack(fill="x", pady=(4, 0))
        ttk.Button(row, text="Set start position...", command=self.fleet_anchor_dialog).pack(side="left")
        ttk.Button(row, text="Open the map", command=lambda: self.fleet_open_page("#map")).pack(side="left", padx=4)
        ttk.Button(row, text="Open storage", command=lambda: self.fleet_open_page("#storage")).pack(side="left", padx=4)
        ttk.Button(row, text="Send job to site...", command=self.fleet_send_dialog).pack(side="left")
        row = ttk.Frame(f)
        row.pack(fill="x", pady=(4, 0))
        ttk.Button(row, text="Colony starter...", command=lambda: self.set_mode("colony")).pack(side="left")
        self.fleet_status = tk.StringVar(value="")
        ttk.Label(f, textvariable=self.fleet_status, wraplength=330, justify="left").pack(anchor="w", pady=2)
        ttk.Label(f, foreground="#555", wraplength=330, justify="left", text=(
            "Where is the turtle?\n"
            "- Same PC (single-player): the address on the Preview tab (http://127.0.0.1:8765) works. In the world's "
            "serverconfig/computercraft-server.toml set the \"$private\" http rule to allow.\n"
            "- Other computers on your network: tick 'Accept turtles from other computers', put this PC's network "
            "address in the Address box (shown above), allow the Windows firewall prompt.\n"
            "- A server you run: do the same in the server's computercraft-server.toml. The turtles call from the "
            "server machine, so the Address must be reachable from there (this PC's LAN or public address with "
            "the port forwarded).\n"
            "Anyone who can reach the address can see the Fleet page and press Stop, so keep it on your own network.")
        ).pack(anchor="w", pady=(4, 0))
        self.fleet_refresh()

    def fleet_address(self):
        url = normalize_live_url(self.live_url_var.get())
        return url or "http://127.0.0.1:8765"

    def fleet_toggle(self):
        self.toggle_live()
        self.fleet_refresh()

    def fleet_page_url(self):
        url = self.fleet_address()
        if self.lan_var.get():
            ip = lan_address()
            if ip:
                port = urllib.parse.urlparse(url).port or 80
                return "http://%s:%d/" % (ip, port)
        return url + "/"

    def fleet_open_page(self, anchor=""):
        if not self.server and not self.start_live():
            return
        self.fleet_refresh()
        webbrowser.open(self.fleet_page_url() + anchor)

    def fleet_copy_address(self):
        self.root.clipboard_clear()
        self.root.clipboard_append(self.fleet_page_url().rstrip("/") if self.lan_var.get() else self.fleet_address())
        self.fleet_status.set("Copied. Use this as the Address for turtles on other computers.")

    def fleet_selected(self):
        sel = self.fleet_tree.selection()
        return int(sel[0]) if sel else None

    def fleet_stop(self):
        tid = self.fleet_selected()
        if tid is None:
            self.fleet_status.set("Pick a turtle in the list first.")
        elif self.fleet.command(tid, "stop"):
            self.fleet_status.set("Stop sent. The turtle gets it with its next report (a few seconds). "
                                  "'carve resume' on it continues later.")
        self.fleet_refresh()

    # ---------------------------------------------------------------- start positions (for the shared map)
    def fleet_save_anchors(self):
        self.cfg["anchors"] = {str(k): list(v) for k, v in self.fleet.typed.items()}
        self.cfg["gods"] = {str(k): v for k, v in self.fleet.gods.items()}
        save_config(self.cfg)

    def fleet_set_anchor(self, tid, x, y, z, face):
        try:
            self.fleet.set_anchor(tid, int(x), int(y), int(z), face)
        except (TypeError, ValueError) as ex:
            self.fleet_status.set("Start position: %s" % ex)
            return False
        self.fleet_status.set("Saved. Turtle #%d started at %s,%s,%s facing %s; it appears on the map." % (tid, x, y, z, face))
        self.fleet_refresh()
        return True

    def fleet_anchor_dialog(self):
        tid = self.fleet_selected()
        if tid is None:
            self.fleet_status.set("Pick a turtle in the list first.")
            return
        old = self.fleet.typed.get(tid, (0, 64, 0, "north"))
        win = tk.Toplevel(self.root)
        win.title("Start position of turtle #%d" % tid)
        win.transient(self.root)
        vs = [tk.StringVar(value=str(n)) for n in old[:3]]
        face = tk.StringVar(value=old[3])
        ttk.Label(win, wraplength=320, justify="left", text=(
            "Where is the block the turtle stood on when it started, in the real world? Press F3 in Minecraft, "
            "stand where the turtle starts and read the XYZ. Then say which way the turtle faced (the direction of "
            "'forward' when it started).")).grid(row=0, column=0, columnspan=4, padx=8, pady=8)
        for i, (lbl, v) in enumerate(zip("XYZ", vs)):
            ttk.Label(win, text=lbl).grid(row=1, column=i * 2, sticky="e", padx=(8, 2))
            ttk.Entry(win, textvariable=v, width=8).grid(row=1, column=i * 2 + 1, sticky="w")
        ttk.Label(win, text="Facing").grid(row=2, column=0, sticky="e", padx=(8, 2), pady=6)
        ttk.Combobox(win, textvariable=face, values=list(FACINGS), state="readonly", width=8).grid(row=2, column=1, sticky="w")

        def ok():
            if self.fleet_set_anchor(tid, vs[0].get(), vs[1].get(), vs[2].get(), face.get()):
                win.destroy()

        def clear():
            self.fleet.clear_anchor(tid)
            win.destroy()
            self.fleet_refresh()
        row = ttk.Frame(win)
        row.grid(row=3, column=0, columnspan=4, pady=8)
        ttk.Button(row, text="Save", command=ok).pack(side="left", padx=4)
        ttk.Button(row, text="Forget it", command=clear).pack(side="left", padx=4)
        ttk.Button(row, text="Cancel", command=win.destroy).pack(side="left", padx=4)

    # ---------------------------------------------------------------- start a program on an idle agent turtle
    def fleet_run(self, tid, slug):
        if self.fleet.command(tid, "run", slug):
            self.fleet_status.set("Order sent: turtle #%d will start '%s' within a few seconds." % (tid, slug))
        else:
            self.fleet_status.set("Turtle #%d is not an idle agent (run the 'Agent' program on it first), or '%s' is not a valid name." % (tid, slug))

    def fleet_run_dialog(self):
        tid = self.fleet_selected()
        if tid is None:
            self.fleet_status.set("Pick an agent turtle in the list first.")
            return
        win = tk.Toplevel(self.root)
        win.title("Start a program on turtle #%d" % tid)
        win.transient(self.root)
        slug = tk.StringVar()
        ttk.Label(win, wraplength=320, justify="left", text=(
            "Pick one of the programs in your repo (press Refresh in 'All designs...' first if the list is empty), "
            "or type its short name.")).grid(row=0, column=0, columnspan=2, padx=8, pady=8)
        box = ttk.Combobox(win, textvariable=slug, width=28)
        box.grid(row=1, column=0, columnspan=2, padx=8)
        box["values"] = [p["slug"] for p in getattr(self, "_remote_entries", []) or []]

        def ok():
            self.fleet_run(tid, slug.get().strip())
            win.destroy()
        row = ttk.Frame(win)
        row.grid(row=2, column=0, columnspan=2, pady=8)
        ttk.Button(row, text="Start", command=ok).pack(side="left", padx=4)
        ttk.Button(row, text="Cancel", command=win.destroy).pack(side="left", padx=4)

    # ---------------------------------------------------------------- send a job to the nearest idle agent
    def fleet_dispatch(self, slug, site, face, foot):
        try:
            tid = self.fleet.dispatch(slug, foot, site, face)
        except ValueError as ex:
            self.fleet_status.set(str(ex))
            return None
        self.fleet_status.set("Sent '%s' to turtle #%d, the nearest idle agent. It walks to %d, %d, %d and starts there." % ((slug, tid) + tuple(site)))
        self.fleet_refresh()
        return tid

    def build_colony_tab(self, f):
        """The colony starter, as a tab of its own: the five turtles are made and uploaded for you; you only give each one's
        start position and tick it once its inventory is filled."""
        saved = self.cfg.get("colony")
        try:
            jobs = colony_foreman(colony_label([clean_auto(j) for j in saved])) if saved else colony_starter()
        except (ValueError, TypeError):
            jobs = colony_starter()
        jobs = colony_foreman(jobs)                           # the foreman always comes first and knows the other jobs
        urls = dict(self.cfg.get("colony_urls") or {})        # job name -> {"cmd", "html"}: how to start it, and its page on GitHub
        plans = self.cfg.get("colony_pos") or {}              # job name -> {"x","y","z","face","filled"}
        ttk.Label(f, text="Foreman", font=("TkDefaultFont", 12, "bold")).pack(anchor="w")
        ttk.Label(f, wraplength=330, justify="left", foreground="#555", text=(
            "One turtle to start by hand. Give it a position, the materials below, and it sets up and runs the rest of the colony. "
            "Type where it stands (world X Y Z from F3, and the way it faces), tick 'Filled' once its inventory is ready.")
                  ).pack(anchor="w", pady=(0, 4))
        adv_body = ttk.Frame(f)                                 # shown by the "Advanced" button at the bottom
        top = ttk.Frame(f)
        top.pack(fill="x", pady=(0, 4))
        ttk.Button(top, text="Upload to GitHub", style="Accent.TButton", command=lambda: self.colony_upload()).pack(side="left")
        ttk.Button(top, text="Update all (latest code)", command=lambda: self.colony_upload(everything=True)).pack(side="left", padx=4)
        ttk.Label(top, text="  app v%s" % VERSION, foreground="#555").pack(side="left")
        web = ttk.Frame(f)
        web.pack(fill="x", pady=(0, 4))
        ttk.Button(web, text="Open Fleet page (map, turtles)", style="Accent.TButton", command=lambda: self.fleet_open_page()).pack(side="left")
        ttk.Button(web, text="3D map", command=lambda: self.fleet_open_page("#3d")).pack(side="left", padx=4)
        ttk.Button(web, text="Foreman: inventory and queue", command=lambda: self.fleet_open_page("#foreman")).pack(side="left")
        fgrid = ttk.Frame(f)                                    # the Foreman's card
        fgrid.pack(fill="x")
        conn = ttk.LabelFrame(adv_body, text="Connection (why turtles don't show up)", padding=4)
        conn.pack(fill="x", pady=(0, 4))
        conn_status = tk.StringVar()
        ttk.Label(conn, textvariable=conn_status, wraplength=320, justify="left").pack(anchor="w")
        crow = ttk.Frame(conn)
        crow.pack(fill="x", pady=2)
        ttk.Label(crow, text="Turtles call:").pack(side="left")
        ttk.Entry(crow, textvariable=self.live_url_var, width=28).pack(side="left", padx=4)

        def lan_changed():
            if self.lan_var.get():
                ip = lan_address()
                if ip and urllib.parse.urlparse(normalize_live_url(self.live_url_var.get()) or "").hostname in ("127.0.0.1", "localhost", None):
                    port = urllib.parse.urlparse(self.fleet_address()).port or 8765
                    self.live_url_var.set("http://%s:%d" % (ip, port))
                conn_status.set("Changed. Upload again so the turtles get the new address.")
            if self.server:
                self.stop_live()
                self.start_live()
        ttk.Checkbutton(conn, text="Turtles run on another computer or a server", variable=self.lan_var, command=lan_changed).pack(anchor="w")
        ping = tk.StringVar()
        prow = ttk.Frame(conn)
        prow.pack(fill="x", pady=2)
        ttk.Label(prow, text="Test on a turtle:").pack(side="left")
        ttk.Entry(prow, textvariable=ping, width=30, state="readonly").pack(side="left", padx=4)
        ttk.Button(prow, text="Copy", width=5, command=lambda: (self.root.clipboard_clear(), self.root.clipboard_append(ping.get()))).pack(side="left")
        ttk.Label(conn, foreground="#777", wraplength=320, justify="left", text=(
            "Run that on any turtle (install the carve menu first). It says if the address is blocked by Minecraft "
            "(computercraft-server.toml: set the \"$private\" http rule to allow) or if nothing answers.")).pack(anchor="w")
        dbg = tk.Text(conn, width=38, height=7, wrap="none", font=("TkFixedFont", 8))
        dbg.pack(fill="x", pady=(4, 0))
        dbg.configure(state="disabled")
        dev = ttk.LabelFrame(adv_body, text="Developer test: one coordinate sets up everything", padding=4)
        dev.pack(fill="x", pady=(0, 4))
        ttk.Label(dev, wraplength=320, justify="left", foreground="#555", text=(
            "Type ONE start cell (world X Y Z from F3). 'Lay out' fills every turtle's position in a row from there. "
            "'Send all to idle agents' hands each job to the nearest idle Agent turtle (run  carve agent  once on each; they need "
            "their own start position), and they walk to their spot and start by themselves.")).pack(anchor="w")
        orow = ttk.Frame(dev)
        orow.pack(fill="x", pady=2)
        ovars = [tk.StringVar(value=str((self.cfg.get("colony_origin") or ["", "", ""])[i])) for i in range(3)]
        for lbl, v in zip("XYZ", ovars):
            ttk.Label(orow, text=lbl).pack(side="left")
            ttk.Entry(orow, textvariable=v, width=7).pack(side="left", padx=(1, 6))
        small = tk.BooleanVar(value=bool(self.cfg.get("colony_test")))
        ttk.Checkbutton(dev, text="Small test sizes (2x2 tree farm, short warehouse, 2 furnaces)", variable=small).pack(anchor="w")
        drow = ttk.Frame(dev)
        drow.pack(fill="x", pady=2)
        basef = ttk.LabelFrame(f, text="Base design (pixel designer)", padding=4)
        basef.pack(fill="x", pady=(0, 4))
        use_base = tk.BooleanVar(value=bool(self.cfg.get("colony_base")))
        base_msg = tk.StringVar()
        ttk.Checkbutton(basef, text="Take every job's position from the stations marked in the Carve editor", variable=use_base).pack(anchor="w")
        ttk.Label(basef, wraplength=320, justify="left", foreground="#555", text=(
            "Draw the base in Carve mode, pick the 'Mark a station' tool and click where each turtle's job starts. The cell where the "
            "turtle T stands is the Foreman: give the Foreman a position below and every marked job follows it, "
            "also when you move a mark later.")).pack(anchor="w")
        ttk.Button(basef, text="Open the pixel designer", command=lambda: self.set_mode("carve")).pack(anchor="w", pady=2)
        ttk.Label(basef, textvariable=base_msg, wraplength=320, justify="left").pack(anchor="w")
        grid = ttk.Frame(adv_body)                              # the other turtles, out of the way
        grid.pack(fill="x")
        rows = []                                              # one dict of vars per job
        summary, status = tk.StringVar(), tk.StringVar()
        faces = list(FACINGS)

        def effective(j):
            return colony_test_variant(j) if small.get() else j

        def effective_all():                                   # every job as it will be uploaded, the foreman's list matching
            return colony_foreman([effective(j) for j in jobs if j["kind"] != "foreman"])

        def persist():
            self.cfg["colony_test"] = bool(small.get())
            self.cfg["colony_origin"] = [v.get() for v in ovars]
            self.cfg["colony_base"] = bool(use_base.get())
            self.cfg["colony"] = list(jobs)
            self.cfg["colony_pos"] = {r["job"]["name"]: {"x": r["x"].get(), "y": r["y"].get(), "z": r["z"].get(), "face": r["face"].get(),
                                                         "filled": r["filled"].get(), "started": r["started"].get()} for r in rows}
            self.cfg["colony_urls"] = dict(urls)
            save_config(self.cfg)

        def position(r):
            try:
                return int(r["x"].get()), int(r["y"].get()), int(r["z"].get())
            except ValueError:
                return None

        def fill_guide_now():
            try:
                fill_guide()
            except NameError:                                  # the first refresh runs before the guide exists
                pass

        busy = []

        def apply_base():
            """Fill the positions of the marked jobs from the base design in the Carve editor."""
            des = self.design
            if not use_base.get():
                base_msg.set("")
                return
            fr = next((r for r in rows if r["job"]["kind"] == "foreman"), None)
            origin = position(fr) if fr else None
            if not des.marks:
                base_msg.set("No stations are marked in the Carve editor yet.")
                return
            if not origin:
                base_msg.set("Give the Foreman a position (X Y Z and facing) below: it is the turtle T of the base design.")
                return
            face = fr["face"].get() if fr["face"].get() in FACINGS else "north"
            spots = base_positions(des, origin, face)
            lower = {n.lower(): v for n, v in spots.items()}
            done, missing = [], []
            for r in rows:
                if r is fr:
                    continue
                v = lower.get(r["job"]["name"].lower())
                if not v:
                    missing.append(r["job"]["name"])
                    continue
                for k, val in zip(("x", "y", "z"), v[:3]):
                    if r[k].get() != str(val):
                        r[k].set(str(val))
                if r["face"].get() != v[3]:
                    r["face"].set(v[3])
                done.append(r["job"]["name"])
            base_msg.set("%d job(s) follow the marks%s%s" % (len(done), ("; no mark for: " + ", ".join(missing)) if missing else "",
                         ("; marks with no job: " + ", ".join(n for n in spots if n.lower() not in {j["name"].lower() for j in jobs})) if any(
                             n.lower() not in {j["name"].lower() for j in jobs} for n in spots) else ""))

        def refresh(*_):
            if busy:
                return
            busy.append(1)
            try:
                apply_base()
            finally:
                busy.pop()
            seen = {t["name"].lower(): t for t in self.fleet.snapshot()}
            addr = normalize_live_url(self.live_url_var.get())
            dbg.configure(state="normal")
            dbg.delete("1.0", "end")
            dbg.insert("1.0", self.fleet.debug_text(12))
            dbg.configure(state="disabled")
            dbg.see("end")
            ping.set("carve ping %s" % (addr or "http://<this PC>:8765"))
            if not conn_status.get().startswith("Changed"):
                conn_status.set(("Fleet server: listening on port %d. " % self.server.port if self.server else
                                 "Fleet server: NOT listening yet (it starts when you upload, or press Start listening on the Fleet tab). ")
                                + ("%d turtle(s) have reported." % len(seen) if seen else "No turtle has reported yet."))
            ready = 0
            for r in rows:
                pos = position(r)
                if pos:
                    self.fleet.plan_position(r["job"]["name"], pos[0], pos[1], pos[2], r["face"].get() if r["face"].get() in FACINGS else "north")
                else:
                    self.fleet.plan_position(r["job"]["name"], 0, 0, 0, None)
                t = seen.get(r["job"]["name"].lower())
                r["state"].set(("running as %s" % (t["label"] or "#%d" % t["id"])) if t else "not started")
                if t and not r["autoticked"]:
                    r["autoticked"] = True
                    r["started"].set(True)                       # it reported in, so it has been started
                if pos and r["filled"].get():
                    ready += 1
            started = sum(1 for r in rows if r["started"].get())
            summary.set("%d of %d turtles have a position and are filled; %d started.%s" % (
                ready, len(rows), started, "  All ready: start them in this order, one by one." if rows and ready == len(rows) and not started else ""))
            fill_guide_now()
            persist()

        def draw():
            jobs[:] = colony_foreman(jobs)
            for w in grid.winfo_children() + fgrid.winfo_children():
                w.destroy()
            del rows[:]
            cnt = {str(grid): 0, str(fgrid): 0}
            for j in jobs:
                g = fgrid if j["kind"] == "foreman" else grid
                p = plans.get(j["name"], {})
                r = {"job": j, "x": tk.StringVar(value=str(p.get("x", ""))), "y": tk.StringVar(value=str(p.get("y", ""))),
                     "z": tk.StringVar(value=str(p.get("z", ""))), "face": tk.StringVar(value=p.get("face", "north")),
                     "filled": tk.BooleanVar(value=bool(p.get("filled"))), "state": tk.StringVar(),
                     "started": tk.BooleanVar(value=bool(p.get("started"))), "cmd": tk.StringVar(), "autoticked": bool(p.get("started"))}
                rows.append(r)
                i = cnt[str(g)]
                cnt[str(g)] += 1
                ttk.Label(g, text=("%s  -  %s" % (j.get("label", ""), j["name"])) if j["kind"] == "foreman" else "%s  -  %s (%s)" % (
                    j.get("label", ""), j["name"], dict(AUTO_KINDS)[j["kind"]].split(" (")[0]),
                          font=("TkDefaultFont", 9, "bold")).grid(row=4 * i, column=0, columnspan=3, sticky="w", pady=(8, 0))
                ttk.Label(g, textvariable=r["state"], foreground="#555").grid(row=4 * i, column=3, columnspan=2, sticky="e", pady=(8, 0))
                ttk.Label(g, text="needs: " + COLONY_NEEDS.get(j["kind"], ""), foreground="#777", wraplength=330, justify="left").grid(
                    row=4 * i + 1, column=0, columnspan=5, sticky="w")
                for c, k in enumerate(("x", "y", "z")):
                    ttk.Entry(g, textvariable=r[k], width=6).grid(row=4 * i + 2, column=c, sticky="w", padx=1)
                    r[k].trace_add("write", refresh)
                ttk.Combobox(g, textvariable=r["face"], values=faces, state="readonly", width=6).grid(row=4 * i + 2, column=3, padx=1)
                r["face"].trace_add("write", refresh)
                r["filled"].trace_add("write", refresh)
                ttk.Checkbutton(g, text="Filled", variable=r["filled"]).grid(row=4 * i + 2, column=4, padx=4)
                r["started"].trace_add("write", refresh)
                u = urls.get(j["name"])
                r["cmd"].set(u["cmd"] if u else "(not uploaded yet)  carve %s" % slugify(j["name"]))
                ttk.Entry(g, textvariable=r["cmd"], width=33, state="readonly").grid(row=4 * i + 3, column=0, columnspan=3, sticky="we", padx=1, pady=(2, 0))
                ttk.Button(g, text="Copy", width=5, command=lambda r=r: (self.root.clipboard_clear(), self.root.clipboard_append(r["cmd"].get()))).grid(
                    row=4 * i + 3, column=3, pady=(2, 0))
                ttk.Checkbutton(g, text="Started", variable=r["started"]).grid(row=4 * i + 3, column=4, padx=4, pady=(2, 0))
            refresh()
        draw()
        add = ttk.Frame(adv_body)
        add.pack(fill="x", pady=6)
        kind = tk.StringVar(value=AUTO_KINDS[0][1])
        ttk.Label(add, text="Add another:").pack(side="left")
        ttk.Combobox(add, textvariable=kind, values=[l for _k, l in AUTO_KINDS], state="readonly", width=24).pack(side="left", padx=4)

        def upload(*_, everything=False):
            self.live_enabled_var.set(True)                    # the hauler, the keeper's page and the Fleet page all need live reporting
            if not self.server:
                self.start_live()                              # ...and something to report to
            conn_status.set("")
            cfg = self.collect_github_cfg()
            live = self.live_url_for_upload()
            if cfg is None or live is None:
                status.set(self.gh_status.get() or "Fill in the GitHub tab first.")
                return
            status.set(("Updating GitHub with this version's code (%d colony programs + your other automation jobs)..." if everything
                        else "Uploading %d programs...") % len(jobs))
            todo = effective_all()

            def work():
                # the first-start programs for turtles the Foreman builds: the Agent and the carve menu
                ag = publish_auto(cfg, clean_auto(AGENT_DEFAULT), live)
                patched = [dict(j, agent_url=ag.get("program_url", ""), launcher_url=ag.get("launcher_url", "")) if j["kind"] == "foreman" else j
                           for j in todo]
                infos = [publish_auto(cfg, j, live) for j in patched]
                extra = 0
                if everything:                                 # every other automation job already in the repo gets rebuilt too
                    have = {auto_slug(j) for j in todo} | {"agent"}
                    for e in read_index(cfg)["programs"]:
                        if e.get("auto") and e.get("slug") not in have:
                            publish_auto(cfg, fetch_remote_auto(cfg, e["slug"]), live)
                            extra += 1
                return infos, extra

            def done(result):
                infos, extra = result
                for j, info in zip(todo, infos):
                    urls[j["name"]] = {"cmd": turtle_commands(info)[1],
                                       "html": info.get("html_url", "")}
                    for r in rows:
                        if r["job"]["name"] == j["name"]:
                            r["cmd"].set(urls[j["name"]]["cmd"])
                persist()
                self.refresh_turtle_commands()
                menu, _p = turtle_commands(infos[-1])
                self.root.clipboard_clear()
                self.root.clipboard_append(menu)
                if everything:
                    status.set("GitHub is up to date with Carve Designer v%s (%s): %d colony programs%s, and the carve menu. "
                               "Each program starts with a line naming the version. Turtles fetch it the next time you run them." % (
                                   VERSION, time.strftime("%H:%M"), len(infos), (" + %d others" % extra) if extra else ""))
                else:
                    status.set("Uploaded %d programs. On each turtle type its command (Copy), then run  job_<name>  (or install the carve menu once and run  carve <name>). "
                               "Tick Started when it is running." % len(infos))
            self.run_bg(work, done, lambda ex: status.set(str(ex)))

        def add_one():
            key = {l: k for k, l in AUTO_KINDS}.get(kind.get())
            if key == "foreman":
                status.set("There is only one foreman; it already sets up all the others.")
                return
            try:
                jobs.append(colony_extra(jobs, key))
            except ValueError as ex:
                status.set(str(ex))
                return
            draw()
            upload()
        def lay_out():
            try:
                origin = tuple(int(v.get()) for v in ovars)
            except ValueError:
                status.set("Type the start cell as three whole numbers (X Y Z).")
                return
            note = ""
            # v7.9: a start cell far from the Foreman is almost certainly a typo or an old coordinate; use a spot 12 blocks east of the Foreman instead.
            fw = self.fleet.foreman_world()
            if fw and max(abs(origin[0] - fw[0]), abs(origin[1] - fw[1]), abs(origin[2] - fw[2])) > 100:   # a typo or an old coordinate: the jobs would walk for hundreds of blocks
                origin = (fw[0] + 12, fw[1], fw[2])
                for v, n in zip(ovars, origin):
                    v.set(str(n))
                note = " (the start cell you typed was far from the Foreman, so I used a spot 12 blocks east of it)"
            spots = colony_layout(effective_all(), origin)
            for r in rows:
                x, y, z = spots[r["job"]["name"]]
                r["x"].set(str(x)); r["y"].set(str(y)); r["z"].set(str(z)); r["face"].set("north")
            status.set("Positions filled in a row from %d %d %d, all facing north.%s Check them, then 'Send all to idle agents'." % (origin + (note,)))

        def send_all():
            sent, failed = [], []
            for r in rows:
                if r["job"]["kind"] == "foreman":                      # it is started by hand, then it does this itself
                    continue
                pos = position(r)
                j = effective(r["job"])
                if not pos:
                    failed.append("%s: no position" % j["name"])
                    continue
                try:
                    tid = self.fleet.dispatch(slugify(j["name"]), auto_footprint(j), pos, r["face"].get() if r["face"].get() in FACINGS else "north")
                except ValueError as ex:
                    failed.append("%s: %s" % (j["name"], ex))
                    continue
                sent.append("%s -> #%d" % (j["name"], tid))
                r["started"].set(True)
            status.set(("Sent: " + ", ".join(sent) + ". " if sent else "") + ("Not sent: " + "; ".join(failed) if failed else "All sent."))
            self.fleet_refresh()
        ttk.Button(drow, text="Lay out", command=lay_out).pack(side="left")
        ttk.Button(drow, text="Send all to idle agents", command=send_all).pack(side="left", padx=4)
        small.trace_add("write", lambda *a: persist())
        ttk.Button(add, text="Add", command=add_one).pack(side="left")
        ttk.Button(add, text="Upload again", command=upload).pack(side="left", padx=6)
        ttk.Label(f, textvariable=summary, font=("TkDefaultFont", 10, "bold"), wraplength=330, justify="left").pack(anchor="w")
        ttk.Label(f, textvariable=status, wraplength=330, foreground="#555", justify="left").pack(anchor="w", pady=(2, 4))
        guide = tk.Text(f, width=38, height=17, wrap="word")
        guide.pack(fill="both", expand=True, pady=4)

        def fill_guide():
            eff = effective_all()
            text = colony_materials_text(eff)
            if guide.get("1.0", "end-1c") != text:
                guide.configure(state="normal")
                guide.delete("1.0", "end")
                guide.insert("1.0", text)
                guide.configure(state="disabled")
        fill_guide()

        adv_open = tk.BooleanVar(value=False)
        adv_btn = ttk.Button(f)

        def toggle_adv():
            adv_open.set(not adv_open.get())
            if adv_open.get():
                adv_body.pack(fill="x", after=adv_btn)
            else:
                adv_body.pack_forget()
            adv_btn.configure(text=("\u25be " if adv_open.get() else "\u25b8 ") + "Advanced: connection test, the other turtles, developer test")
        adv_btn.configure(command=toggle_adv)
        adv_btn.pack(anchor="w", pady=(6, 0))
        toggle_adv(); toggle_adv()                             # sets the label, stays closed
        self.colony_advanced = toggle_adv
        self.colony_frames = {"foreman": fgrid, "others": grid, "advanced": adv_body}

        def tick():                                            # keep "running as ..." up to date
            refresh()
            self.root.after(3000, tick)
        self.root.after(3000, tick)
        self.colony_rows, self.colony_summary, self.colony_upload, self.colony_ping = rows, summary, upload, ping
        self.marks_changed = refresh
        use_base.trace_add("write", lambda *a: refresh())
        self.mark_box["values"] = [r["job"]["name"] for r in rows]
        self.colony_base = {"use": use_base, "msg": base_msg}
        self.colony_dev = {"origin": ovars, "small": small, "lay_out": lay_out, "send_all": send_all, "status": status}

    def fleet_send_dialog(self):
        win = tk.Toplevel(self.root)
        win.title("Send a job to a site")
        win.transient(self.root)
        slug, face = tk.StringVar(), tk.StringVar(value="north")
        vs = [tk.StringVar(value="0"), tk.StringVar(value="64"), tk.StringVar(value="0")]
        sel = self.fleet_selected()
        for r in self.fleet.snapshot():
            if r["id"] == sel and r["world"]:
                for v, n in zip(vs, r["world"]):
                    v.set(str(n))
        entries = {}
        ttk.Label(win, wraplength=340, justify="left", text=(
            "The job goes to the nearest idle agent turtle. It walks to the start cell you give (where the job's turtle "
            "would stand, in world coordinates from F3), faces the way you choose, and runs the program. "
            "A job that would overlap one already sent is refused.")).grid(row=0, column=0, columnspan=4, padx=8, pady=8)
        ttk.Label(win, text="Program").grid(row=1, column=0, sticky="e", padx=(8, 2))
        box = ttk.Combobox(win, textvariable=slug, width=26)
        box.grid(row=1, column=1, columnspan=3, sticky="w")
        for i, (lbl, v) in enumerate(zip("XYZ", vs)):
            ttk.Label(win, text=lbl).grid(row=2, column=i, sticky="e", padx=(8, 2), pady=6)
            ttk.Entry(win, textvariable=v, width=7).grid(row=3, column=i, sticky="w", padx=(8, 2))
        ttk.Label(win, text="Facing").grid(row=2, column=3, sticky="w", padx=(8, 2))
        ttk.Combobox(win, textvariable=face, values=list(FACINGS), state="readonly", width=8).grid(row=3, column=3, sticky="w")
        status = tk.StringVar()
        ttk.Label(win, textvariable=status, wraplength=340, foreground="#555").grid(row=5, column=0, columnspan=4, padx=8)

        def fill(entry_list):
            for e in entry_list:
                entries[e["slug"]] = e
            box["values"] = sorted(entries)
        fill(getattr(self, "_remote_entries", []) or [])

        def load():
            cfg = self.collect_github_cfg(need_token=False)
            if cfg is None:
                status.set(self.gh_status.get())
                return
            status.set("Loading the program list...")
            self.run_bg(lambda: read_index(cfg), lambda idx: (fill(idx["programs"]), status.set("%d programs." % len(idx["programs"]))),
                        lambda ex: status.set(str(ex)))

        def send():
            e = entries.get(slug.get().strip())
            try:
                site = [int(v.get()) for v in vs]
            except ValueError:
                status.set("The coordinates must be whole numbers.")
                return
            foot = e.get("foot") if e else None
            if self.fleet_dispatch(slug.get().strip(), site, face.get(), foot):
                win.destroy()
            else:
                status.set(self.fleet_status.get())
        row = ttk.Frame(win)
        row.grid(row=4, column=0, columnspan=4, pady=8)
        ttk.Button(row, text="Load program list", command=load).pack(side="left", padx=4)
        ttk.Button(row, text="Send", command=send).pack(side="left", padx=4)
        ttk.Button(row, text="Cancel", command=win.destroy).pack(side="left", padx=4)

    def fleet_forget(self):
        tid = self.fleet_selected()
        if tid is not None:
            self.fleet.forget(tid)
        self.fleet_refresh()

    def fleet_refresh(self):
        """Redraw the list; repeats once a second while the window exists."""
        try:
            if not self.fleet_tree.winfo_exists():
                return
        except tk.TclError:
            return
        if self.fleet_job is not None:
            try:
                self.root.after_cancel(self.fleet_job)
            except Exception:
                pass
        keep = self.fleet_selected()
        rows = self.fleet.snapshot()
        have = {int(i) for i in self.fleet_tree.get_children()}
        for gone in have - {r["id"] for r in rows}:
            self.fleet_tree.delete(str(gone))
        for r in rows:
            prog = "%d/%d" % (r["n"], r["total"]) if r["total"] else (str(r["n"]) if r["n"] else "")
            seen = "now" if r["age"] < 5 else "%ds" % r["age"] if r["age"] < 120 else "%dm" % (r["age"] // 60)
            where = "%d,%d,%d" % tuple(r["world"]) if r["world"] else "start %+d,%+d,%+d" % (r["x"], r["y"], r["z"])
            vals = (r["label"] or r["name"] or "#%d" % r["id"], r["kind"], r["state"], prog, r["fuel"], where, seen, r["msg"])
            if str(r["id"]) in self.fleet_tree.get_children():
                self.fleet_tree.item(str(r["id"]), values=vals)
            else:
                self.fleet_tree.insert("", "end", iid=str(r["id"]), values=vals)
        if keep is not None and self.fleet_tree.exists(str(keep)):
            self.fleet_tree.selection_set(str(keep))
        if self.server:
            self.fleet_btn.configure(text="Stop listening")
            self.fleet_info.set("Listening on port %d. Page: %s  -  %d turtle(s) known." % (
                self.server.port, self.fleet_page_url(), len(rows)))
        else:
            self.fleet_btn.configure(text="Start listening")
            self.fleet_info.set("Not listening.")
        self.fleet_job = self.root.after(1000, self.fleet_refresh)
# GUI part: the main window, styling (apply_style) and the scrollable, resizable layout. The App class mixes in all the GUI parts.
# ====================================================================== GUI: main window
COL_BG = "#1e2227"


class App(ViewMixin, GitMixin, BlocksMixin, AutoMixin, FleetMixin):
    TOP = 28                    # room above the grid for the "FORWARD" label

    def __init__(self, root, cfg=None):
        self.root = root
        root.title("Carve Designer v" + VERSION)
        sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
        root.minsize(min(900, sw), min(600, sh))
        root.update_idletasks()
        if root.geometry().startswith("1x1"):                   # nobody sized the window yet: open it big, but inside the screen
            root.geometry("%dx%d" % (min(1360, int(sw * 0.88)), min(900, int(sh * 0.88))))
        self.apply_style()
        self.cfg = cfg if cfg is not None else load_config()
        load_texpack()
        TEX["mode"] = "imported" if (self.cfg.get("texture_mode") == "imported" and TEX["tiles"]) else "builtin"
        self.mode = "edit"                       # edit | preview | live
        self.design = Design()
        self.layer = 1
        # editing state
        self.undo = []
        self.items, self.cache = {}, {}
        self.cs = self.ox = self.oy = 0
        self.preview = {}
        self.unreachable = set()
        self.total = self.skipped = 0
        self.dragging = False
        self.paint_val = True
        self.start_cell = self.last_cell = None
        self._trail_cells = set()
        self._relayout_job = None
        # viewer state
        self.vdesign = self.view = self.sim = None
        self.play_idx = 0
        self.playing = False
        self._play_job = None
        self._scale_busy = False
        # live state
        self.server = None
        self.live_q = queue.Queue()
        self.sessions = {}
        self.live_current = None
        self.live_job = None
        # other
        self.dwin = None
        self.last_upload = None
        # tk variables
        c = self.cfg
        self.brush = None                        # slot painted cells will get, None = plain digging
        self.sel_slot = 16                       # slot picked in the inventory display
        self.item_var = tk.StringVar()
        self.brush_var = tk.StringVar(value="")
        self.supply_var = tk.StringVar(value="")
        self.torch_gap = tk.IntVar(value=4)
        self.pattern_var = tk.StringVar()
        self.torch_mode_var = tk.StringVar()
        self.marks, self.mcache = {}, {}
        self.tool = tk.StringVar(value="pencil")
        self.mark_name, self.mark_face = tk.StringVar(value="Tree farm"), tk.StringVar(value="forward")
        self._marks_sig = None
        self.hollow = tk.BooleanVar(value=False)
        self.chest_var = tk.BooleanVar(value=True)
        self.size_vars = [tk.IntVar(value=9), tk.IntVar(value=9), tk.IntVar(value=4)]
        self.name_var = tk.StringVar()
        self.follow_var = tk.BooleanVar(value=True)
        self.speed_var = tk.IntVar(value=6)
        self.seek_var = tk.DoubleVar(value=0)
        self.hover_var = tk.StringVar(value="")
        self.info_var = tk.StringVar(value="")
        self.stats_var = tk.StringVar(value="")
        self.gh_status = tk.StringVar(value="")
        self.dstatus = tk.StringVar(value="")
        self.live_status = tk.StringVar(value="Not listening.")
        self.repo_var = tk.StringVar(value=c.get("repo", ""))
        self.branch_var = tk.StringVar(value=c.get("branch", "main"))
        self.folder_var = tk.StringVar(value=c.get("folder", DEFAULT_FOLDER))
        self.token_var = tk.StringVar(value=c.get("token", "") or os.environ.get("GITHUB_TOKEN", ""))
        self.remember_var = tk.BooleanVar(value=bool(c.get("token")))
        self.live_enabled_var = tk.BooleanVar(value=bool(c.get("live_enabled", True)))
        self.seal_var = tk.BooleanVar(value=False)
        self.skin_var = tk.StringVar(value="Green turtle")
        self.share_var = tk.BooleanVar(value=bool(c.get("share", True)))
        self.share_url_var = tk.StringVar(value="")
        self.live_url_var = tk.StringVar(value=c.get("live_url", DEFAULT_LIVE_URL))
        self.lan_var = tk.BooleanVar(value=bool(c.get("lan", False)))
        self.build_ui()
        self.load_initial()
        root.protocol("WM_DELETE_WINDOW", self.on_close)

    # ------------------------------------------------------------------ plumbing
    def sd(self):
        """The design currently drawn (the real one, or the one being previewed / watched)."""
        return self.vdesign if (self.mode != "edit" and self.vdesign is not None) else self.design

    def info(self, title, msg):
        messagebox.showinfo(title, msg)

    def error(self, title, msg):
        messagebox.showerror(title, msg)

    def confirm(self, title, msg):
        return messagebox.askyesno(title, msg)

    def ask_save_path(self, **kw):
        return filedialog.asksaveasfilename(**kw)

    def ask_open_path(self, **kw):
        return filedialog.askopenfilename(**kw)

    def run_bg(self, fn, on_ok, on_err):
        """Run fn() on a worker thread; call on_ok(result) / on_err(exception) in the UI thread."""
        box = queue.Queue()

        def work():
            try:
                box.put((True, fn()))
            except Exception as ex:                       # shown to the user, never crashes the window
                box.put((False, ex))

        threading.Thread(target=work, daemon=True).start()

        def poll():
            try:
                ok, val = box.get_nowait()
            except queue.Empty:
                self.root.after(60, poll)
                return
            (on_ok if ok else on_err)(val)

        self.root.after(60, poll)

    # ------------------------------------------------------------------ look
    def apply_style(self):
        """One clean, flat look: soft grey panels, white fields, one blue accent, a readable system font."""
        import tkinter.font as tkfont
        root = self.root
        st = ttk.Style()
        try:
            st.theme_use("clam")
        except Exception:
            pass
        have = set(tkfont.families())
        family = next((f for f in ("Segoe UI", "SF Pro Text", "Helvetica Neue", "Inter", "Noto Sans", "DejaVu Sans", "Arial") if f in have), "TkDefaultFont")
        for name in ("TkDefaultFont", "TkTextFont", "TkMenuFont", "TkHeadingFont", "TkCaptionFont"):
            try:
                tkfont.nametofont(name).configure(family=family, size=10)
            except Exception:
                pass
        BG, CARD, FG, MUTED, LINE = "#f3f4f7", "#ffffff", "#1c2230", "#667085", "#d5d9e0"
        ACC, ACC_DK, BTN, BTN_HI = "#2f6fed", "#1f57c7", "#e7eaf0", "#dbe0e9"
        self.theme = {"bg": BG, "card": CARD, "fg": FG, "muted": MUTED, "line": LINE, "accent": ACC}
        root.configure(background=BG)
        root.option_add("*Listbox.background", CARD)
        root.option_add("*Listbox.relief", "flat")
        root.option_add("*Text.relief", "flat")
        root.option_add("*Menu.background", CARD)
        root.option_add("*Menu.foreground", FG)
        root.option_add("*Menu.activeBackground", ACC)
        root.option_add("*Menu.activeForeground", "#ffffff")
        st.configure(".", background=BG, foreground=FG, bordercolor=LINE, lightcolor=BG, darkcolor=BG, troughcolor="#e6e9ef",
                     focuscolor=ACC, selectbackground=ACC, selectforeground="#ffffff", insertcolor=FG)
        st.configure("TFrame", background=BG)
        st.configure("TLabel", background=BG, foreground=FG)
        st.configure("TButton", background=BTN, foreground=FG, padding=(14, 7), relief="flat", borderwidth=0, focusthickness=0)
        st.map("TButton", background=[("disabled", "#eceef2"), ("pressed", "#cfd5e0"), ("active", BTN_HI)],
               foreground=[("disabled", "#a3a9b5")])
        st.configure("Accent.TButton", background=ACC, foreground="#ffffff")
        st.map("Accent.TButton", background=[("pressed", ACC_DK), ("active", ACC_DK)])
        st.configure("Toolbutton", background=BTN, foreground=FG, padding=(16, 8), relief="flat", borderwidth=0)
        st.map("Toolbutton", background=[("selected", ACC), ("pressed", ACC_DK), ("active", BTN_HI)],
               foreground=[("selected", "#ffffff")])
        for kind in ("TCheckbutton", "TRadiobutton"):
            st.configure(kind, background=BG, foreground=FG, padding=2)
            st.map(kind, background=[("active", BG)], indicatorcolor=[("selected", ACC), ("!selected", CARD)])
        st.configure("TEntry", fieldbackground=CARD, foreground=FG, bordercolor=LINE, padding=4)
        st.map("TEntry", bordercolor=[("focus", ACC)])
        st.configure("TCombobox", fieldbackground=CARD, background=BTN, foreground=FG, bordercolor=LINE, arrowcolor=MUTED, padding=4)
        st.map("TCombobox", fieldbackground=[("readonly", CARD)], bordercolor=[("focus", ACC)], selectbackground=[("readonly", CARD)],
               selectforeground=[("readonly", FG)])
        st.configure("TSpinbox", fieldbackground=CARD, bordercolor=LINE, arrowcolor=MUTED, padding=3)
        st.configure("TNotebook", background=BG, borderwidth=0, tabmargins=(0, 4, 0, 0))
        st.configure("TNotebook.Tab", background=BG, foreground=MUTED, padding=(11, 8), borderwidth=0)
        st.map("TNotebook.Tab", background=[("selected", CARD), ("active", "#e9ecf2")], foreground=[("selected", ACC)])
        st.configure("TLabelframe", background=BG, bordercolor=LINE, relief="solid", borderwidth=1)
        st.configure("TLabelframe.Label", background=BG, foreground=MUTED, font=(family, 9, "bold"))
        st.configure("TScrollbar", background="#c9cfda", troughcolor=BG, bordercolor=BG, arrowcolor=MUTED, relief="flat", gripcount=0)
        st.map("TScrollbar", background=[("active", "#aeb6c4")])
        st.configure("TScale", background=BG, troughcolor="#dfe3ea")
        st.configure("Treeview", background=CARD, fieldbackground=CARD, foreground=FG, rowheight=24, borderwidth=0)
        st.map("Treeview", background=[("selected", ACC)], foreground=[("selected", "#ffffff")])
        st.configure("Treeview.Heading", background=BTN, foreground=FG, relief="flat", padding=(8, 5), font=(family, 9, "bold"))
        st.configure("TProgressbar", background=ACC, troughcolor="#e1e5ec", borderwidth=0)
        st.configure("TSeparator", background=LINE)
        st.configure("TPanedwindow", background=BG)

    # ------------------------------------------------------------------ layout
    def build_ui(self):
        r = self.root
        r.rowconfigure(0, weight=1)
        left = ttk.Frame(r)
        left.grid(row=0, column=0, sticky="nsew")
        left.columnconfigure(0, weight=1)
        left.rowconfigure(0, weight=1)
        self.canvas = tk.Canvas(left, bg=COL_BG, highlightthickness=0, width=640, height=600)
        self.canvas.grid(row=0, column=0, sticky="nsew")
        ttk.Label(left, textvariable=self.hover_var, anchor="w").grid(row=1, column=0, sticky="ew", padx=6, pady=2)

        self.left = left
        side = ttk.Frame(r, padding=(10, 8))
        side.grid(row=0, column=1, sticky="nsew")
        r.columnconfigure(0, weight=3)                          # the grid and the panel share extra room (set_mode shifts it)
        r.columnconfigure(1, weight=1)
        bar = ttk.Frame(side)
        bar.pack(fill="x", pady=(0, 6))
        self.mode_var = tk.StringVar(value="colony")
        for text, val in (("Colony (turtles)", "colony"), ("Carve by hand", "carve")):
            ttk.Radiobutton(bar, text=text, value=val, variable=self.mode_var, style="Toolbutton",
                            command=lambda: self.set_mode(self.mode_var.get())).pack(side="left", padx=(0, 4))
        row = self.design_row = ttk.Frame(side)
        row.pack(fill="x")
        ttk.Label(row, text="Design").pack(side="left")
        self.name_entry = ttk.Entry(row, textvariable=self.name_var, width=20)
        self.name_entry.pack(side="left", padx=4)
        self.name_entry.bind("<Return>", lambda e: self.commit_name())
        self.name_entry.bind("<FocusOut>", lambda e: self.commit_name())
        ttk.Button(row, text="New design", command=self.new_design).pack(side="left")
        ttk.Button(row, text="All designs...", command=self.open_designs_window).pack(side="left", padx=(3, 0))
        row = self.layer_row = ttk.Frame(side)
        row.pack(fill="x", pady=6)
        ttk.Label(row, text="Layer").pack(side="left")
        ttk.Button(row, text="\u2212", width=3, command=lambda: self.set_layer(self.layer - 1)).pack(side="left", padx=(6, 0))
        self.layer_lbl = ttk.Label(row, text="", width=8, anchor="center")
        self.layer_lbl.pack(side="left")
        ttk.Button(row, text="+", width=3, command=lambda: self.set_layer(self.layer + 1)).pack(side="left")
        ttk.Label(row, text="(wheel / PgUp / PgDn)", foreground="#666").pack(side="left", padx=6)

        nb = self.nb = ttk.Notebook(side)
        nb.pack(fill="both", expand=True)
        self.tabs = {}
        builders = (("Colony", self.build_colony_tab), ("Edit", self.build_edit_tab), ("Blocks", self.build_blocks_tab),
                    ("Preview / Live", self.build_view_tab), ("Automation", self.build_auto_tab), ("Fleet", self.build_fleet_tab),
                    ("GitHub", self.build_github_tab))
        self.tab_inner = {}
        for title, _b in builders:
            f = ttk.Frame(nb)
            nb.add(f, text=title)
            self.tabs[title] = f
            self.tab_inner[title] = self.make_scrollable(f)
        for title, build in sorted(builders, key=lambda b: b[0] == "Colony"):      # the colony tab needs the Fleet tab's server object
            build(self.tab_inner[title])

        self.nb_ready = True
        self.set_mode(self.cfg.get("mode") if self.cfg.get("mode") in ("colony", "carve") else "colony")

        c = self.canvas
        c.bind("<ButtonPress-1>", lambda e: self.on_press(e, False))
        c.bind("<B1-Motion>", self.on_motion)
        c.bind("<ButtonRelease-1>", self.on_release)
        for b in (2, 3):
            c.bind("<ButtonPress-%d>" % b, lambda e: self.on_press(e, True))
            c.bind("<B%d-Motion>" % b, self.on_motion)
            c.bind("<ButtonRelease-%d>" % b, self.on_release)
        c.bind("<Motion>", self.on_hover)
        c.bind("<MouseWheel>", self.on_wheel)
        c.bind("<Button-4>", lambda e: self.set_layer(self.layer + 1))
        c.bind("<Button-5>", lambda e: self.set_layer(self.layer - 1))
        c.bind("<Configure>", self.on_configure)
        r.bind("<Prior>", lambda e: self.set_layer(self.layer + 1))
        r.bind("<Next>", lambda e: self.set_layer(self.layer - 1))
        r.bind("<Control-z>", lambda e: self.do_undo())

    def make_scrollable(self, outer):
        """A frame inside `outer` that scrolls (scrollbar, mouse wheel) when the window is too small for its content."""
        canvas = tk.Canvas(outer, highlightthickness=0, borderwidth=0, width=330, height=300, background=self.theme["bg"])
        bar = ttk.Scrollbar(outer, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=bar.set)
        bar.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)
        inner = ttk.Frame(canvas, padding=8)
        win = canvas.create_window((0, 0), window=inner, anchor="nw")

        def on_inner(_e=None):
            canvas.configure(scrollregion=canvas.bbox("all"))
        inner.bind("<Configure>", on_inner)

        def fit():                                            # the panel is as wide as its widest widget needs (once, after it is built)
            kids = [c.winfo_reqwidth() for c in inner.winfo_children()]
            canvas.configure(width=min(480, max(300, (max(kids) if kids else 300) + 18)))
        outer.after(300, fit)
        wrap_job = [None]

        def rewrap(width):                                    # paragraphs follow the panel's width
            wrap_job[0] = None
            target = max(240, min(780, width - 70))

            def walk(w):
                for k in w.winfo_children():
                    if isinstance(k, (ttk.Label, tk.Label)):
                        try:
                            cur = int(float(str(k.cget("wraplength"))))
                        except (ValueError, tk.TclError):
                            cur = 0
                        if cur and not hasattr(k, "_wl0"):
                            k._wl0 = cur
                        if hasattr(k, "_wl0") and k._wl0 >= 280:
                            k.configure(wraplength=target)
                    walk(k)
            try:
                walk(inner)
            except tk.TclError:
                pass

        def on_canvas(e):                                     # the content is at most 820 px wide and centred in a wide window
            w = min(e.width, 820)
            canvas.itemconfigure(win, width=w)
            canvas.coords(win, max(0, (e.width - w) // 2), 0)
            if wrap_job[0] is not None:
                canvas.after_cancel(wrap_job[0])
            wrap_job[0] = canvas.after(90, lambda: rewrap(w))
        canvas.bind("<Configure>", on_canvas)

        def wheel(e):
            top, bottom = canvas.yview()
            if top <= 0 and bottom >= 1:
                return                                        # everything fits: nothing to scroll
            d = -1 if (getattr(e, "num", 0) == 4 or getattr(e, "delta", 0) > 0) else 1
            canvas.yview_scroll(d * 3, "units")
        for w in (canvas, inner):
            w.bind("<Enter>", lambda e: (outer.bind_all("<MouseWheel>", wheel), outer.bind_all("<Button-4>", wheel), outer.bind_all("<Button-5>", wheel)))
            w.bind("<Leave>", lambda e: None if str(outer.winfo_containing(e.x_root, e.y_root) or "").startswith(str(outer)) else
                   (outer.unbind_all("<MouseWheel>"), outer.unbind_all("<Button-4>"), outer.unbind_all("<Button-5>")))
        inner.scroll_canvas = canvas
        return inner

    def set_mode(self, mode):
        """Colony: only the turtle tabs (starter, Automation, Fleet, GitHub). Carve by hand: the design grid, layer controls and
        the Edit / Blocks / Preview tabs, hiding the colony starter."""
        if mode not in ("colony", "carve") or not getattr(self, "nb_ready", False):
            return
        self.mode_var.set(mode)
        carve_tabs = ("Edit", "Blocks", "Preview / Live")
        self.root.columnconfigure(0, weight=0 if mode == "colony" else 3)
        self.root.columnconfigure(1, weight=1)
        if mode == "colony":
            self.left.grid_remove()
            self.design_row.pack_forget()
            self.layer_row.pack_forget()
            for t in carve_tabs:
                self.nb.hide(self.tabs[t])
            self.nb.add(self.tabs["Colony"])
            self.nb.select(self.tabs["Colony"])
            if not getattr(self, "_colony_auto", False) and (self.token_var.get().strip() or os.environ.get("GITHUB_TOKEN")):
                self._colony_auto = True                  # automatic: put the five programs on GitHub the first time, if a token is saved
                self.root.after(400, self.colony_upload)
        else:
            self.left.grid()
            self.design_row.pack(fill="x", before=self.nb)
            self.layer_row.pack(fill="x", pady=6, before=self.nb)
            self.nb.hide(self.tabs["Colony"])
            for t in carve_tabs:
                self.nb.add(self.tabs[t])
            self.nb.select(self.tabs["Edit"])
        self.cfg["mode"] = mode
        try:
            save_config(self.cfg)
        except Exception:
            pass

    def build_edit_tab(self, p):
        bold = ("TkDefaultFont", 10, "bold")
        ttk.Label(p, text="Tool", font=bold).pack(anchor="w")
        for text, val in (("Pencil (drag to paint)", "pencil"), ("Rectangle", "rect"),
                          ("Ellipse", "ellipse"), ("Place turtle", "turtle"), ("Mark a station (base design)", "station")):
            ttk.Radiobutton(p, text=text, value=val, variable=self.tool).pack(anchor="w")
        mrow = ttk.Frame(p)
        mrow.pack(fill="x", pady=(0, 2))
        ttk.Label(mrow, text="  Station:").pack(side="left")
        self.mark_box = ttk.Combobox(mrow, textvariable=self.mark_name, width=16, values=self.station_names())
        self.mark_box.pack(side="left", padx=2)
        ttk.Combobox(mrow, textvariable=self.mark_face, values=list(MARK_FACES), state="readonly", width=7).pack(side="left")
        ttk.Label(p, foreground="#777", wraplength=300, justify="left", text=(
            "  Click a cell to say where that turtle's job starts (right-click removes). The turtle start cell T is the Foreman. "
            "The Colony tab can take every job's position from these marks.")).pack(anchor="w")
        ttk.Checkbutton(p, text="Hollow (outline only)", variable=self.hollow).pack(anchor="w", pady=(2, 0))
        ttk.Label(p, textvariable=self.brush_var, foreground="#b35c00").pack(anchor="w", pady=(0, 6))

        ttk.Label(p, text="Dig order", font=bold).pack(anchor="w")
        self.pattern_box = ttk.Combobox(p, textvariable=self.pattern_var, state="readonly", width=34,
                                        values=[label for _k, label in PATTERNS])
        self.pattern_box.pack(anchor="w", pady=(0, 6))
        self.pattern_box.bind("<<ComboboxSelected>>", lambda e: self.pick_pattern())

        ttk.Label(p, text="This layer", font=bold).pack(anchor="w")
        row = ttk.Frame(p)
        row.pack(fill="x")
        for text, op in (("Fill layer", "fill"), ("Clear layer", "clear"), ("Invert layer", "invert")):
            ttk.Button(row, text=text, command=lambda o=op: self.layer_op(o)).pack(side="left")
        row = ttk.Frame(p)
        row.pack(fill="x", pady=(2, 6))
        ttk.Button(row, text="Copy layer up", command=lambda: self.copy_layer(1)).pack(side="left")
        ttk.Button(row, text="Copy layer down", command=lambda: self.copy_layer(-1)).pack(side="left")

        ttk.Label(p, text="Shapes and templates", font=bold).pack(anchor="w")
        row = ttk.Frame(p)
        row.pack(fill="x", pady=(0, 6))
        ttk.Button(row, text="Shapes...", command=self.open_shapes).pack(side="left")
        ttk.Button(row, text="Templates...", command=self.open_templates).pack(side="left")
        ttk.Button(row, text="Import build...", command=self.import_schematic).pack(side="left")

        ttk.Label(p, text="Whole box", font=bold).pack(anchor="w")
        row = ttk.Frame(p)
        row.pack(fill="x", pady=(0, 6))
        ttk.Button(row, text="Fill whole box", command=lambda: self.all_op(True)).pack(side="left")
        ttk.Button(row, text="Clear whole box", command=lambda: self.all_op(False)).pack(side="left")

        ttk.Label(p, text="Size  (right x forward x up)", font=bold).pack(anchor="w")
        row = ttk.Frame(p)
        row.pack(fill="x", pady=(0, 6))
        for v in self.size_vars:
            ttk.Spinbox(row, from_=1, to=MAXDIM, width=4, textvariable=v).pack(side="left", padx=(0, 3))
        ttk.Button(row, text="Apply size", command=self.apply_size).pack(side="left", padx=3)

        ttk.Checkbutton(p, text="Chest directly behind turtle", variable=self.chest_var,
                        command=self.toggle_chest).pack(anchor="w")
        ttk.Checkbutton(p, text="Plug lava / water above and below (needs spare cobble)", variable=self.seal_var,
                        command=self.toggle_seal).pack(anchor="w", pady=(0, 6))
        ttk.Label(p, textvariable=self.stats_var, justify="left", wraplength=300).pack(anchor="w", pady=(0, 8))

        row = ttk.Frame(p)
        row.pack(fill="x")
        ttk.Button(row, text="Estimate...", command=self.open_estimate).pack(side="left")
        ttk.Button(row, text="Undo", command=self.do_undo).pack(side="left", padx=2)
        ttk.Button(row, text="Import design...", command=self.open_file).pack(side="left", padx=2)
        ttk.Button(row, text="Export design...", command=self.save_file).pack(side="left")

        ttk.Label(p, foreground="#666", justify="left", wraplength=330, text=(
            "Left-drag selects, right-drag erases. Orange = will be dug, red = not connected "
            "(skipped), green T = turtle, blue C = chest.")).pack(anchor="w", pady=(8, 0))

    # ------------------------------------------------------------------ loading / saving
    def load_initial(self):
        import_old_design()
        design = None
        last = self.cfg.get("last_design")
        if last:
            try:
                design = library_load(last)
            except Exception:
                design = None
        if design is None:
            for e in library_list():
                try:
                    design = library_load(e["slug"])
                    break
                except Exception:
                    continue
        if design is None:
            design = Design()
            design.name = "My first design"
        self.set_design(design)

    def set_design(self, design):
        self.design = design
        self.undo = []
        self.name_var.set(design.name)
        self.chest_var.set(design.chest)
        self.seal_var.set(design.seal)
        self.skin_var.set(dict(SKINS)[design.skin])
        for v, n in zip(self.size_vars, (design.w, design.d, design.h)):
            v.set(n)
        self.layer = max(1, min(design.h, design.ty))
        self.brush = None
        self.sel_slot = 16
        self.recompute()
        self.relayout(force=True)
        self.refresh_inventory()
        self.autosave()

    def autosave(self):
        try:
            library_save(self.design)
            self.cfg["last_design"] = self.design.slug()
            save_config(self.cfg)
        except OSError:
            pass

    def new_design(self):
        self.exit_view()
        self.commit_name()
        design = Design()
        design.name = unique_name("Untitled", {e["slug"] for e in library_list()})
        self.set_design(design)

    def commit_name(self):
        if self.mode != "edit":
            return
        old, new = self.design.name, clean_name(self.name_var.get())
        if new == old:
            self.name_var.set(new)
            return
        if slugify(new) != slugify(old) and slugify(new) in {e["slug"] for e in library_list()}:
            self.error("Name in use", "There is already a design called '%s' on this computer." % new)
            self.name_var.set(old)
            return
        if slugify(new) != slugify(old):
            library_delete(old)
        self.design.name = new
        self.name_var.set(new)
        self.after_edit()

    def open_file(self):
        path = self.ask_open_path(filetypes=[("Carve design", "*.json"), ("All files", "*.*")])
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                new = Design.from_json(json.load(f))
        except Exception as ex:
            self.error("Import", "Could not read that design:\n%s" % ex)
            return
        new.name = unique_name(new.name, {e["slug"] for e in library_list()})
        self.exit_view()
        self.set_design(new)

    def save_file(self):
        path = self.ask_save_path(defaultextension=".json", initialfile=self.design.slug() + ".json",
                                  filetypes=[("Carve design", "*.json")])
        if path:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(self.design.to_json(), f)

    def on_close(self):
        try:
            self.autosave()
            self.cfg["lan"] = bool(self.lan_var.get())
            save_config(self.cfg)
            self.stop_live()
        finally:
            self.root.destroy()

    # ------------------------------------------------------------------ canvas geometry
    def on_configure(self, _e):
        if self._relayout_job is None:
            self._relayout_job = self.root.after(30, self._do_relayout)

    def _do_relayout(self):
        self._relayout_job = None
        self.relayout()

    def fit(self):
        sd = self.sd()
        cw = self.canvas.winfo_width()
        ch = self.canvas.winfo_height()
        if cw < 60 or ch < 60:
            cw, ch = int(self.canvas.cget("width")), int(self.canvas.cget("height"))
        cs = int(max(8, min(44, (cw - 16) / sd.w, (ch - self.TOP - 12) / (sd.d + 1))))
        return cs, (cw - sd.w * cs) // 2, self.TOP, cw

    def relayout(self, force=False):
        cs, ox, oy, cw = self.fit()
        sd = self.sd()
        key = (cs, ox, oy, sd.w, sd.d)
        if force or key != getattr(self, "_built_key", None):
            self.cs, self.ox, self.oy, self.cw = cs, ox, oy, cw
            self._built_key = key
            self.build_canvas_items()
        self.refresh_layer()

    def cell_box(self, x, z):
        cs, d = self.cs, self.sd().d
        x0 = self.ox + (x - 1) * cs
        y0 = self.oy + (d - z) * cs
        return x0, y0, x0 + cs, y0 + cs

    def build_canvas_items(self):
        c, sd = self.canvas, self.sd()
        c.delete("all")
        self.items, self.cache = {}, {}
        self.marks, self.mcache = {}, {}
        for z in range(1, sd.d + 1):
            for x in range(1, sd.w + 1):
                self.items[(x, z)] = c.create_rectangle(*self.cell_box(x, z), fill="#000", outline="#20242a")
        font = ("TkDefaultFont", max(7, int(self.cs * 0.5)), "bold")
        self.top_label = c.create_text(self.cw // 2, 13, fill="#8b949e", text="", font=("TkDefaultFont", 10))
        self.turtle_txt = c.create_text(0, 0, text="T", fill="#102a06", state="hidden", font=font)
        self.chest_txt = c.create_text(0, 0, text="C", fill="#0b2a44", state="hidden", font=font)
        self.chest_box = c.create_rectangle(0, 0, 0, 0, fill="#4aa3df", outline="#20242a", state="hidden")
        self.chest_box_txt = c.create_text(0, 0, text="C", fill="#0b2a44", state="hidden", font=font)

    # ------------------------------------------------------------------ drawing
    def style_for(self, x, z):
        sd, y = self.sd(), self.layer
        alt = (x + z) % 2 == 0
        cell = (x, y, z)
        outline, width = "#20242a", 1
        if self.mode == "edit":
            if (x, y - 1, z) in sd.sel and cell not in sd.sel:
                outline, width = "#6fb1ff", 2
            if cell == sd.turtle:
                fill = self.skin_color(sd)
            elif (x, z) in self.preview:
                fill = "#ffe28a" if self.preview[(x, z)] else "#8a8f98"
            elif sd.chest and cell == sd.chest_cell:
                fill = "#4aa3df"
            elif cell in sd.sel:
                if cell in self.unreachable:
                    fill = "#d9534f" if alt else "#e57a77"
                else:
                    fill = "#f0a030" if alt else "#f6b653"
            else:
                fill = "#3b3f46" if alt else "#454a52"
            return fill, outline, width
        v = self.view
        if cell in self._trail_cells:
            outline, width = "#33d6ff", 2
        if v and cell == v.pos:
            fill = self.skin_color(sd)
        elif sd.chest and cell == sd.chest_cell:
            fill = "#4aa3df"
        elif v and cell in v.mined:
            fill = "#2e7d4f" if alt else "#348a58"                 # already dug
        elif cell in sd.sel:
            fill = ("#d9534f" if alt else "#e57a77") if cell in self.unreachable else ("#f0a030" if alt else "#f6b653")
        else:
            fill = "#3b3f46" if alt else "#454a52"
        return fill, outline, width

    def marker_for(self, x, z):
        """(colour, placed-already) for a cell that will receive a block, else None."""
        sd = self.sd()
        cell = (x, self.layer, z)
        slot = sd.place.get(cell)
        if slot is None or slot not in sd.inv:
            return None
        done = bool(self.view and self.mode != "edit" and cell in self.view.placed)
        return (item_color(sd.inv[slot]), done, sd.inv[slot])

    def draw_marker(self, x, z):
        mk = self.marker_for(x, z)
        tag = "mk%d_%d" % (x, z)
        if mk is None:
            if self.mcache.get((x, z)) is not None:
                self.canvas.delete(tag)
                self.mcache[(x, z)] = None
            return
        if self.mcache.get((x, z)) == (mk, self.cs):
            return
        self.canvas.delete(tag)
        x0, y0, x1, y1 = self.cell_box(x, z)
        bank = self.icon_bank() if self.cs >= 20 else None
        img = bank.get(mk[2], max(1, (int(self.cs) - 4) // 16)) if bank else None
        if img is not None:
            self.canvas.create_image((x0 + x1) / 2, (y0 + y1) / 2, image=img, tags=tag)
            if mk[1]:
                self.canvas.create_rectangle(x0 + 2, y0 + 2, x1 - 2, y1 - 2, outline="#3ddc84", width=2, tags=tag)
        else:
            inset = self.cs * (0.16 if mk[1] else 0.3)
            self.canvas.create_rectangle(x0 + inset, y0 + inset, x1 - inset, y1 - inset,
                                         fill=mk[0], outline="#101316", width=1, tags=tag)
        self.mcache[(x, z)] = (mk, self.cs)

    def refresh_cells(self, cells):
        for (x, z) in cells:
            item = self.items.get((x, z))
            if item is None:
                continue
            st = self.style_for(x, z)
            if self.cache.get(item) != st:
                self.canvas.itemconfigure(item, fill=st[0], outline=st[1], width=st[2])
                self.cache[item] = st
            self.draw_marker(x, z)

    def refresh_layer(self):
        sd, c, cs = self.sd(), self.canvas, self.cs
        if not self.items:
            return
        self._trail_cells = {t for t in self.view.trail if t[1] == self.layer} if self.view else set()
        self.refresh_cells(list(self.items.keys()))
        # turtle marker
        if self.mode == "edit":
            tcell, txt = sd.turtle, "T"
        else:
            tcell, txt = self.view.pos, ARROWS.get(self.view.face, "T")
        if tcell[1] == self.layer:
            x0, y0, x1, y1 = self.cell_box(tcell[0], tcell[2])
            c.coords(self.turtle_txt, (x0 + x1) / 2, (y0 + y1) / 2)
            c.itemconfigure(self.turtle_txt, text=txt, state="normal")
            c.tag_raise(self.turtle_txt)
        else:
            c.itemconfigure(self.turtle_txt, state="hidden")
        # chest marker: inside the grid, or just below it when the turtle is on the back row
        cc = sd.chest_cell
        if sd.chest and cc is not None and cc[1] == self.layer:
            x0, y0, x1, y1 = self.cell_box(cc[0], cc[2])
            c.coords(self.chest_txt, (x0 + x1) / 2, (y0 + y1) / 2)
            c.itemconfigure(self.chest_txt, state="normal")
            c.tag_raise(self.chest_txt)
        else:
            c.itemconfigure(self.chest_txt, state="hidden")
        if sd.chest and sd.tz == 1 and sd.ty == self.layer:
            x0 = self.ox + (sd.tx - 1) * cs
            y0 = self.oy + sd.d * cs + 3
            c.coords(self.chest_box, x0 + 2, y0, x0 + cs - 2, y0 + cs - 4)
            c.coords(self.chest_box_txt, x0 + cs / 2, y0 + (cs - 4) / 2)
            c.itemconfigure(self.chest_box, state="normal")
            c.itemconfigure(self.chest_box_txt, state="normal")
        else:
            c.itemconfigure(self.chest_box, state="hidden")
            c.itemconfigure(self.chest_box_txt, state="hidden")
        self.draw_marks()
        label = {"edit": "▲ FORWARD  (the turtle faces this way)",
                 "preview": "PREVIEW (simulated route)   ▲ forward",
                 "live": "LIVE – the real turtle   ▲ forward"}[self.mode]
        c.itemconfigure(self.top_label, text=label, fill="#8b949e" if self.mode == "edit" else "#33d6ff")
        self.layer_lbl.configure(text="%d / %d" % (self.layer, sd.h))
        if self.mode == "edit":
            places = len(build_place(sd))
            nbad = len(bad_torches(sd))
            self.stats_var.set("Selected: %d\nWill mine: %d\nUnreachable (skipped): %d\n"
                               "Fuel needed: up to ~%d%s" % (
                                   len(sd.sel), self.total, self.skipped, self.total,
                                   ("\nBlocks to place: %d" % places) if places else "")
                               + (("\nTorches that can't go in: %d (they need a dug cell above\nand a solid floor under them)" % nbad)
                                  if nbad else ""))

    def station_names(self):
        rows = getattr(self, "colony_rows", None)
        names = [r["job"]["name"] for r in rows] if rows else ["Foreman", "Storage keeper", "Tree farm", "Smelter", "Compressor", "Hauler"]
        return names

    def draw_marks(self):
        c = self.canvas
        c.delete("mark")
        sig = tuple(sorted(self.design.marks.items()))
        if sig != self._marks_sig:
            self._marks_sig = sig
            cb = getattr(self, "marks_changed", None)
            if cb:
                cb()
        if self.mode != "edit":
            return
        arrows = {"forward": "▲", "right": "▶", "back": "▼", "left": "◀"}
        for n, (x, y, z, f) in self.design.marks.items():
            if y != self.layer:
                continue
            x0, y0, x1, y1 = self.cell_box(x, z)
            c.create_rectangle(x0 + 1, y0 + 1, x1 - 1, y1 - 1, outline="#ff5ccb", width=2, tags="mark")
            c.create_text((x0 + x1) / 2, (y0 + y1) / 2, text=n[:1].upper() + arrows[f], fill="#ff9be0", tags="mark",
                          font=("TkDefaultFont", max(7, int(self.cs * 0.38)), "bold"))

    def recompute(self):
        run, self.total, self.skipped = build_run(self.design)
        d = self.design
        hidden = {d.chest_cell} if (d.chest and d.chest_cell) else set()
        self.unreachable = d.sel - run - hidden

    def after_edit(self):
        self.recompute()
        self.refresh_layer()
        self.refresh_inventory()
        self.autosave()

    # ------------------------------------------------------------------ editing
    def snapshot(self):
        self.undo.append(self.design.copy())
        if len(self.undo) > 60:
            self.undo.pop(0)

    def do_undo(self):
        if self.mode != "edit" or not self.undo:
            return
        old = self.undo.pop()
        resized = (old.w, old.d, old.h) != (self.design.w, self.design.d, self.design.h)
        old.name = self.design.name                   # names are not part of undo
        self.design = old
        self.chest_var.set(old.chest)
        self.seal_var.set(old.seal)
        self.skin_var.set(dict(SKINS)[old.skin])
        self.layer = max(1, min(self.layer, old.h))
        for v, n in zip(self.size_vars, (old.w, old.d, old.h)):
            v.set(n)
        self.recompute()
        self.relayout(force=resized)
        self.refresh_inventory()
        self.autosave()

    def set_layer(self, n):
        n = max(1, min(self.sd().h, n))
        if n != self.layer:
            self.layer = n
            self.refresh_layer()

    def on_wheel(self, e):
        self.set_layer(self.layer + (1 if e.delta > 0 else -1))

    def cell_at(self, e):
        sd = self.sd()
        if self.cs <= 0:
            return None
        x = int((e.x - self.ox) // self.cs) + 1
        row = int((e.y - self.oy) // self.cs)
        z = sd.d - row
        if 1 <= x <= sd.w and 1 <= z <= sd.d:
            return (x, z)
        return None

    def on_hover(self, e):
        cell = self.cell_at(e)
        self.hover_var.set("x %d   z %d   layer %d" % (cell[0], cell[1], self.layer) if cell else "")

    @staticmethod
    def line(a, b):
        (x0, z0), (x1, z1) = a, b
        n = max(abs(x1 - x0), abs(z1 - z0))
        if n == 0:
            return [a]
        return [(round(x0 + (x1 - x0) * i / n), round(z0 + (z1 - z0) * i / n)) for i in range(n + 1)]

    def paint(self, x, y, z, on):
        slot = self.brush if (on and self.brush in self.design.inv) else None
        self.design.set_cell(x, y, z, on, slot=slot)

    def on_press(self, e, erase):
        if self.mode != "edit":
            return
        cell = self.cell_at(e)
        if cell is None:
            return
        x, z = cell
        y, d = self.layer, self.design
        tool = self.tool.get()
        if tool == "station":
            self.snapshot()
            try:
                if erase:
                    for n in [n for n, m in d.marks.items() if m[:3] == (x, y, z)]:
                        del d.marks[n]
                else:
                    d.set_mark(self.mark_name.get(), x, y, z, self.mark_face.get())
            except ValueError as ex:
                self.hover_var.set(str(ex))
                return
            self.after_edit()
            return
        if tool == "turtle":
            self.snapshot()
            d.tx, d.ty, d.tz = x, y, z
            d.sel.discard(d.turtle)
            self.tool.set("pencil")
            self.after_edit()
            return
        self.snapshot()
        self.dragging = True
        want = (True, self.brush if self.brush in d.inv else None)
        self.paint_val = False if erase else d.cell_state((x, y, z)) != want
        self.start_cell = self.last_cell = cell
        if tool == "pencil":
            self.paint(x, y, z, self.paint_val)
            self.refresh_cells([cell])
        else:
            self.update_preview(cell)

    def on_motion(self, e):
        if not self.dragging or self.mode != "edit":
            return
        cell = self.cell_at(e)
        if cell is None or cell == self.last_cell:
            return
        if self.tool.get() == "pencil":
            touched = self.line(self.last_cell, cell)
            for (x, z) in touched:
                self.paint(x, self.layer, z, self.paint_val)
            self.refresh_cells(touched)
        else:
            self.update_preview(cell)
        self.last_cell = cell

    def shape_cells(self, a, b):
        (x0, z0), (x1, z1) = a, b
        xa, xb, za, zb = min(x0, x1), max(x0, x1), min(z0, z1), max(z0, z1)
        hollow = self.hollow.get()
        cells = set()
        if self.tool.get() == "rect":
            for x in range(xa, xb + 1):
                for z in range(za, zb + 1):
                    if hollow and xa < x < xb and za < z < zb:
                        continue
                    cells.add((x, z))
            return cells
        cx, cz = (xa + xb) / 2.0, (za + zb) / 2.0
        ra, rb = (xb - xa) / 2.0 + 0.5, (zb - za) / 2.0 + 0.5

        def inside(x, z, ra, rb):
            return ra > 0 and rb > 0 and ((x - cx) / ra) ** 2 + ((z - cz) / rb) ** 2 <= 1.0

        for x in range(xa, xb + 1):
            for z in range(za, zb + 1):
                if inside(x, z, ra, rb) and not (hollow and inside(x, z, ra - 1, rb - 1)):
                    cells.add((x, z))
        return cells

    def update_preview(self, cell):
        old = set(self.preview)
        self.preview = {c: self.paint_val for c in self.shape_cells(self.start_cell, cell)}
        self.refresh_cells(old | set(self.preview))

    def on_release(self, e):
        if not self.dragging:
            return
        self.dragging = False
        if self.preview:
            for (x, z) in self.preview:
                self.paint(x, self.layer, z, self.paint_val)
            self.preview = {}
        self.after_edit()

    def layer_op(self, op):
        if self.mode != "edit":
            return
        d, y = self.design, self.layer
        self.snapshot()
        for z in range(1, d.d + 1):
            for x in range(1, d.w + 1):
                if op == "fill":
                    self.paint(x, y, z, True)
                elif op == "clear":
                    d.set_cell(x, y, z, False)
                else:
                    self.paint(x, y, z, (x, y, z) not in d.sel)
        self.after_edit()

    def copy_layer(self, step):
        d, y = self.design, self.layer
        to = y + step
        if self.mode != "edit" or not 1 <= to <= d.h:
            return
        self.snapshot()
        for z in range(1, d.d + 1):
            for x in range(1, d.w + 1):
                d.set_cell(x, to, z, (x, y, z) in d.sel, slot=d.place.get((x, y, z)))
        self.layer = to
        self.after_edit()

    def all_op(self, on):
        if self.mode != "edit":
            return
        d = self.design
        self.snapshot()
        for y in range(1, d.h + 1):
            for z in range(1, d.d + 1):
                for x in range(1, d.w + 1):
                    self.paint(x, y, z, on)
        self.after_edit()

    def apply_size(self):
        if self.mode != "edit":
            return
        try:
            w, dd, h = (int(v.get()) for v in self.size_vars)
        except (tk.TclError, ValueError):
            self.error("Size", "Enter whole numbers for the size.")
            return
        if not all(1 <= n <= MAXDIM for n in (w, dd, h)):
            self.error("Size", "Each size must be between 1 and %d." % MAXDIM)
            return
        self.snapshot()
        self.design.resize(w, dd, h)
        self.layer = max(1, min(self.layer, h))
        self.recompute()
        self.relayout(force=True)
        self.refresh_inventory()
        self.autosave()

    def open_estimate(self):
        """Fuel, time and how many stacks of each block the job needs - from the exact route."""
        if self.mode != "edit":
            return
        self.commit_name()
        design = self.design.copy()
        if build_run(design)[1] == 0:
            self.info("Estimate", "Select some cells connected to the turtle first.")
            return
        self.stats_var.set("Working out the estimate...")

        def work():
            return estimate(design)

        def done(est):
            self.recompute()
            self.refresh_layer()
            top = tk.Toplevel(self.root)
            top.title("Estimate - " + design.name)
            top.transient(self.root)
            f = ttk.Frame(top, padding=12)
            f.pack(fill="both", expand=True)
            txt = tk.Text(f, width=64, height=min(24, 6 + len(est["lines"]) + 3 * len(est["warnings"])), wrap="word")
            txt.pack(fill="both", expand=True)
            txt.insert("1.0", estimate_text(est))
            txt.configure(state="disabled")
            ttk.Button(f, text="Close", command=top.destroy).pack(anchor="e", pady=(8, 0))
            self.estimate_window = top
            self.last_estimate = est
        self.run_bg(work, done, lambda ex: self.error("Estimate", str(ex)))

    def import_schematic(self, path=None):
        """Turn a Litematica / WorldEdit / structure-block file into a dig-and-place design."""
        if self.mode != "edit":
            return
        path = path or self.ask_open_path(filetypes=[("Minecraft builds", "*.litematic *.schem *.nbt"),
                                                      ("All files", "*.*")])
        if not path:
            return
        try:
            des, rep = schematic_design(load_schematic(path),
                                        name=clean_name(os.path.splitext(os.path.basename(path))[0]) or "Imported build")
        except SchematicError as ex:
            self.error("Import build", str(ex))
            return
        self.exit_view()
        self.commit_name()
        des.name = unique_name(des.name, {e["slug"] for e in library_list()})
        self.set_design(des)
        msg = "Imported %d blocks (%d x %d x %d), %d kinds." % ((rep["blocks"],) + tuple(rep["size"]) + (rep["kinds"],))
        if rep["mapped"]:
            msg += " The turtle holds 8 kinds, so %d rarer ones became the most similar of the 8." % rep["mapped"]
        if rep["unreachable"]:
            msg += " %d blocks float apart from the rest and will be skipped." % rep["unreachable"]
        self.info("Import build", msg)
        return rep

    def open_shapes(self):
        if self.mode != "edit":
            return
        top = tk.Toplevel(self.root)
        top.title("Shapes")
        top.transient(self.root)
        f = ttk.Frame(top, padding=12)
        f.pack(fill="both", expand=True)
        d = self.design
        ttk.Label(f, text="Fills the whole box (%d x %d x %d). Change the size first if you want it bigger."
                  % (d.w, d.d, d.h), wraplength=360).pack(anchor="w", pady=(0, 8))
        kind = tk.StringVar(value="cylinder")
        for key, label in SHAPES:
            ttk.Radiobutton(f, text=label, value=key, variable=kind).pack(anchor="w")
        hollow = tk.BooleanVar(value=False)
        caps = tk.BooleanVar(value=True)
        repl = tk.BooleanVar(value=True)
        ttk.Checkbutton(f, text="Hollow (only the outer skin)", variable=hollow).pack(anchor="w", pady=(8, 0))
        ttk.Checkbutton(f, text="...with floor and ceiling", variable=caps).pack(anchor="w", padx=(18, 0))
        ttk.Checkbutton(f, text="Replace what is there now", variable=repl).pack(anchor="w", pady=(4, 0))
        note = ("The selected block (if any) is placed in every cell." if self.brush in d.inv
                else "Tip: pick a block on the Blocks tab first to build the shape out of it.")
        ttk.Label(f, text=note, foreground="#666", wraplength=360).pack(anchor="w", pady=(6, 8))

        def go():
            cells = shape_cells(kind.get(), d.w, d.d, d.h, hollow.get(), caps.get())
            self.snapshot()
            apply_cells(self.design, cells, replace=repl.get(),
                        slot=self.brush if self.brush in self.design.inv else None)
            self.layer = max(1, min(self.design.h, self.design.ty))
            self.recompute()
            self.relayout(force=True)
            self.after_edit()
            top.destroy()
        row = ttk.Frame(f)
        row.pack(fill="x")
        ttk.Button(row, text="Apply", command=go).pack(side="left")
        ttk.Button(row, text="Close", command=top.destroy).pack(side="left", padx=4)
        self.shapes_dialog = top

    def open_templates(self):
        if self.mode != "edit":
            return
        top = tk.Toplevel(self.root)
        top.title("Templates")
        top.transient(self.root)
        f = ttk.Frame(top, padding=12)
        f.pack(fill="both", expand=True)
        ttk.Label(f, text="Start a new design from a ready-made one.", wraplength=360).pack(anchor="w", pady=(0, 8))

        def make(key):
            top.destroy()
            self.exit_view()
            self.commit_name()
            design = template_design(key)
            design.name = unique_name(design.name, {e["slug"] for e in library_list()})
            self.set_design(design)
        for key, title, blurb, (w, dd, h), _fn in TEMPLATES:
            row = ttk.Frame(f)
            row.pack(fill="x", pady=2)
            ttk.Button(row, text=title, width=30, command=lambda k=key: make(k)).pack(side="left")
            ttk.Label(row, text="%dx%dx%d  %s" % (w, dd, h, blurb), foreground="#666").pack(side="left", padx=6)
        self.templates_dialog = top

    def toggle_seal(self):
        if self.mode != "edit":
            self.seal_var.set(self.design.seal)
            return
        self.snapshot()
        self.design.seal = bool(self.seal_var.get())
        self.autosave()

    def toggle_chest(self):
        if self.mode != "edit":
            self.chest_var.set(self.design.chest)
            return
        self.snapshot()
        self.design.chest = self.chest_var.get()
        self.after_edit()


def main():
    if not TK_OK:
        print("This program needs Python with tkinter (included with the python.org installers;\n"
              "on Linux install the python3-tk package).")
        sys.exit(1)
    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
