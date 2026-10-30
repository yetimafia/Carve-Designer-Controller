# Changelog

Versions before 7.3 are only partly recorded: the 2.x-3.x entries come from the feature list at the top of `src/p1_core.py`, and the
7.x entries before 7.3 are listed together because their exact numbers were not written down.

## 8.3
* The project is now called Replicating Turtles (window title and file name `replicating_turtles.py`). The original dig designer is the
  "Carve Tool (dig by hand)" switch. Settings stay in `~/.carve_designer`, and the in-game `carve` menu command is unchanged, so nothing has to be re-set up.

## 8.2
* Smelter splits each pile evenly over all furnaces so they run at the same time; charcoal is the preferred fuel, a two-round reserve is
  kept and the surplus goes to the output chest (and on into storage).
* Every turtle burns charcoal before coal when it refuels itself.

## 8.1
* A Foreman's jobs are placed by offset from the Foreman itself (right and ahead, 10 blocks between areas); typed coordinates are not used.
* The Foreman is always shown with the crafting grid.

## 8.0
* Inventory tab ("Inventory - <turtle name>"); click a turtle in the 3D map to open it.
* Crafting-capable turtles show slots 1,2,3,5,6,7,9,10,11 as a crafting grid and slot 16 as a gold result slot; slots are smaller.
* Every turtle reports its inventory and whether it can craft.

## 7.9
* "Lay out" compares the typed start cell with the Foreman's position and uses a spot next to the Foreman when it is far away.

## 7.8
* Stop on the Fleet page also removes the automatic restart.
* Turtles with the same name are numbered (1), (2) on the page.
* Colony layout leaves 10 blocks between jobs.

## 7.7
* New hand-drawn item pictures: ingots, gems, dust, coal, stick, paper, sugar cane, saplings, pickaxe, furnace, crafting table, hopper, cobblestone,
  stone, glass, glass pane, chest and the ComputerCraft computer, turtle, disk drive and floppy disk.

## 7.6
* The Foreman's build code was rewritten. Everything stays in the two chests; each craft empties the turtle, takes exactly the ingredients,
  crafts and stores the result. Stops crafting after a few failed tries instead of wasting materials.

## 7.5
* Shopping list has spare redstone.

## 7.4
* The Foreman crafts a hopper and loads the floppy through it (needs 5 more iron and a chest).

## 7.x before 7.3 (numbers not recorded)
* Foreman tab with inventory and crafting queue; item pictures on the Storage and Foreman tabs.
* Foreman remembers what is in its chests and fetches by that list; refuels from the chest early; gives kits and fuel to the turtles it places
  (through a kit chest); positions of every placed turtle are known.
* Crafting always happens with an empty inventory (this pack requires it); corrected disk drive recipe (7 stone + 2 redstone).
* Professional, resizable UI; button to open the Fleet page; restored turtle face in the 3D map.

## 2.x - 3.0 (from the feature list in `src/p1_core.py`)
* 2.0-2.2: Automation tab (tree farm, smelter, crafter). 2.3: Fleet tab. 2.4-2.6: shared world map, scout, agent.
* 2.7-2.8: miner, send jobs to idle agents. 2.9-3.0: haulers, storage keeper and the Storage tab.
