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
