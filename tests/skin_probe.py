"""Opens the 3D page in headless Chromium, switches through every turtle skin, prints JSON."""
import json, sys
from playwright.sync_api import sync_playwright

page_path, shot = sys.argv[1], sys.argv[2]
out = {"errs": [], "skins": {}}
with sync_playwright() as p:
    br = p.chromium.launch(args=["--use-gl=swiftshader", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist"])
    pg = br.new_page(viewport={"width": 900, "height": 600})
    pg.on("pageerror", lambda e: out["errs"].append(str(e)))
    pg.on("console", lambda m: out["errs"].append(m.text) if m.type == "error" else None)
    pg.goto("file://" + page_path)
    pg.wait_for_timeout(1000)
    out["options"] = pg.evaluate("Array.from(document.querySelectorAll('#skin option')).map(o => o.value)")
    out["start"] = pg.evaluate("CARVE_VIEWER.skin()")
    for sk in ["classic", "bee", "sea", "golem", "custom"]:
        pg.evaluate("CARVE_VIEWER.setSkin('%s')" % sk)
        pg.wait_for_timeout(250)
        out["skins"][sk] = [pg.evaluate("CARVE_VIEWER.skin()"), pg.is_visible("#skinbody")]
    pg.select_option("#skin", "bee")
    pg.wait_for_timeout(200)
    out["after_select"] = pg.evaluate("CARVE_VIEWER.skin()")
    pg.screenshot(path=shot)
    pg.goto("file://" + page_path + "?again=1#skin=golem")
    pg.wait_for_timeout(600)
    out["hash"] = pg.evaluate("CARVE_VIEWER.skin()")
    br.close()
print(json.dumps(out))
