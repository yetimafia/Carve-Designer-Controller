#!/usr/bin/env python3
"""Assemble src/*.py (+ the .lua templates) into the single-file replicating_turtles.py."""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "src")
PARTS = ["p1_core.py", "p2_model.py", "p2a_icons.py", "p2c_tiles.py", "p2d_texpack.py", "p2e_shapes.py", "p2f_schematic.py", "p2g_auto.py", "p2b_three.py", "p3_sim.py", "p3b_viewer.py", "p3c_estimate.py", "p3d_fleet.py", "p4_github.py",
         "p5_viewmixin.py", "p6_gitmixin.py", "p6b_blocksmixin.py", "p6c_automixin.py", "p6d_fleetmixin.py", "p7_app.py"]


def build():
    out = ""
    for name in PARTS:
        out += open(os.path.join(SRC, name), encoding="utf-8").read()

    def include(m):
        text = open(os.path.join(SRC, m.group(1)), encoding="utf-8").read()
        assert "'''" not in text, m.group(1) + " contains '''"
        return text

    out = re.sub(r"@@INCLUDE:([\w.]+)@@", include, out)
    ver = re.search(r'^VERSION = "([0-9.]+)"', out, re.M).group(1)
    out = out.replace("@@VERSION@@", ver)
    target = os.path.join(HERE, "replicating_turtles.py")
    with open(target, "w", encoding="utf-8", newline="\n") as f:
        f.write(out)
    compile(out, target, "exec")
    return target, out.count("\n")


if __name__ == "__main__":
    t, n = build()
    print("built %s (%d lines)" % (t, n))
