"""Build harness.lua = patched mock CC environment + test cases runner."""
h = open('mock_head.lua').read()

def sub(old, new, count=1):
    global h
    assert old in h, "missing: " + old[:60]
    h = h.replace(old, new, count)

sub('local CASES_DIR = ...  or "."', 'local CASES_DIR = rawget(_G, "CASES_DIR") or "."')
sub('local OUT = {}', 'local OUT = {}\nOUT_START = 0')
sub('if abortAfter and actions >= abortAfter then abortAfter = nil; error("Terminated", 0) end',
    'if abortAfter and actions >= abortAfter then abortAfter = nil; error("Terminated", 0) end\n  if TERM_PENDING then TERM_PENDING = false; error("Terminated", 0) end')
sub('shell = { getRunningProgram = function() return "carve" end }',
    '''SHELL_RUNS = {}
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
write = function(s) term.write(s) end''')
sub('textutils = {', 'textutils = {\n  unserialiseJSON = function(s) return PY_JSON(s) end,')
sub('sleep = function() sleepCount = sleepCount + 1; if sleepCount > 5000 then error("too many sleeps", 0) end end',
    '''local fakeTime = 0
os.clock = function() return fakeTime end
sleep = function(n) fakeTime = fakeTime + (n or 1); sleepCount = sleepCount + 1; if sleepCount > 5000 then error("too many sleeps " .. debug.traceback(), 0) end end''')
sub('read = function() return table.remove(readQueue, 1) or "" end',
    'read = function()\n  if #readQueue == 0 then error("read queue empty", 0) end\n  return table.remove(readQueue, 1)\nend')
sub('local noTool = false', 'local noTool = false\nlocal evlog, itemKinds = nil, 18')
sub('  actions = actions + 1', '  actions = actions + 1\n  fakeTime = fakeTime + 0.4')
sub('    digCount = digCount + 1\n', '    digCount = digCount + 1\n    if evlog then evlog[#evlog + 1] = ("d,%d,%d,%d"):format(x, y, z) end\n')
sub('    T.x, T.y, T.z = x, y, z\n', '    T.x, T.y, T.z = x, y, z\n    if evlog then evlog[#evlog + 1] = ("m,%d,%d,%d"):format(x, y, z) end\n')
sub('turtle.turnRight = function() bump(); T.f = (T.f + 1) % 4; return true end',
    'turtle.turnRight = function() bump(); T.f = (T.f + 1) % 4; if evlog then evlog[#evlog + 1] = "t," .. (T.f + 1) end; return true end')
sub('turtle.turnLeft = function() bump(); T.f = (T.f + 3) % 4; return true end',
    'turtle.turnLeft = function() bump(); T.f = (T.f + 3) % 4; if evlog then evlog[#evlog + 1] = "t," .. (T.f + 1) end; return true end')
# fewer distinct item kinds -> the inventory doesn't fill up in small jobs (needed to compare routes)
assert 'local h = (x * 7 + y * 13 + z * 29) % 18' in h
h = h.replace('local h = (x * 7 + y * 13 + z * 29) % 18', 'local h = (x * 7 + y * 13 + z * 29) % itemKinds')
sub('  term.write(table.concat(t, " "))\n  cx, cy = 1, cy + 1', '  PRINTED[#PRINTED + 1] = table.concat(t, " ")\n  term.write(table.concat(t, " "))\n  cx, cy = 1, cy + 1')
sub('local OUT = {}', 'local OUT = {}\nPRINTED = {}')
h = h.replace('error("too many sleeps", 0)', 'error("too many sleeps " .. debug.traceback(), 0)')
open('harness.lua', 'w').write(h + "\n" + open('harness_tail2.lua').read())
print("harness assembled")
