import sys, os, random
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import replicating_turtles as cd
out = sys.argv[1]
# a 9x9x3 hall with a cobblestone floor, glass roof and floor torches, plus a skipped (unconnected) block
d = cd.Design(9, 9, 4); d.name = "Dining Hall"; d.tx, d.ty, d.tz = 5, 2, 1
for y in (1, 2, 3, 4):
    for z in range(1, 10):
        for x in range(1, 10):
            if y == 1 or (1 < x < 9 and 1 < z < 9) or y < 3:
                d.set_cell(x, y, z, True)
d.set_cell(1, 4, 9, True)
d.set_slot_item(16, cd.TORCH); d.set_slot_item(15, "minecraft:cobblestone")
for z in range(2, 9):
    for x in range(2, 9): d.place[(x, 1, z)] = 15
d.torch_mode = "first"
cd.auto_torches(d, 3, 16)
sim = cd.simulate(d)
open(out, "w", encoding="utf-8").write(cd.build_viewer_html(d, sim))
print("events", len(sim.events), "digs", sim.digs, "moves", sim.moves, "places", sim.places, "turns", sim.turns, "skipped", len(d.sel) - cd.build_run(d)[1] - 1)
