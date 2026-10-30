# Builds the stand-alone 3D page (viewer3d.html + turtle3d.js) that shows the turtle's whole route in a browser.
# ============================================================ the 3D page (opens in any web browser)
VIEWER_TEMPLATE = r'''@@INCLUDE:viewer3d.html@@'''
TURTLE3D_JS = r'''@@INCLUDE:turtle3d.js@@'''


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
