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
