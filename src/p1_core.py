#!/usr/bin/env python3
"""
Replicating Turtles v@@VERSION@@ - a colony of CC: Tweaked turtles that crafts and starts itself (the Foreman),
plus the original "Carve Tool": design a dig shape on your PC, put the turtle program on GitHub, watch the turtle work.

Run:   python replicating_turtles.py        (Python 3.8+ with tkinter; nothing else to install)

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

VERSION = "8.3"     # bump by 0.1 for every idea/feature batch the user adds
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
TURTLE_TEMPLATE = r'''@@INCLUDE:turtle_job.lua@@'''
LAUNCHER_TEMPLATE = r'''@@INCLUDE:launcher.lua@@'''
