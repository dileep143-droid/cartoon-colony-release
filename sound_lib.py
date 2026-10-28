"""Collect free/open sound-effect libraries and save them to the owner's PRIVATE Google Drive ("Kulfi Sound Library/<source>/").
Nothing is kept on GitHub. Before every upload the Drive free space is checked; when it runs out the job stops cleanly.
Files already on Drive (same name and size) are skipped, so re-running only fills the gaps.
Usage: python sound_lib.py quota | zenodo <record_id> <name> | url <name> <url> | bbc <category> | mixkit
       python sound_lib.py archive <archive_org_id> <name> | pixabay | mendeley <dataset_id> <name>"""
import concurrent.futures as cf, gzip, json, os, re, shutil, sys, time, urllib.request, zipfile
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
UA = {"User-Agent": "kulfi-sound-library/0.1 (personal archive)"}
ROOT = "Kulfi Sound Library"
def get(u, data=None, tries=5, headers=None):
    for i in range(tries):
        try:
            return urllib.request.urlopen(urllib.request.Request(u, data=data, headers={**UA, **(headers or {})}), timeout=300).read()
        except Exception as e:
            last = e; time.sleep(5 * (i + 1))
    raise last
def fetch_to(u, path):
    for i in range(5):
        try:
            with urllib.request.urlopen(urllib.request.Request(u, headers=UA), timeout=600) as r, open(path, "wb") as f:
                shutil.copyfileobj(r, f, 8 << 20)
            return
        except Exception as e:
            last = e; time.sleep(15 * (i + 1))
    raise last
c = Credentials.from_authorized_user_info(json.loads(os.environ["DRIVE_TOKEN"]))
if not c.valid: c.refresh(Request())
dr = build("drive", "v3", credentials=c, cache_discovery=False)
def folder(nm, parent=None):
    q = f"name='{nm}' and mimeType='application/vnd.google-apps.folder' and trashed=false" + (f" and '{parent}' in parents" if parent else "")
    f = dr.files().list(q=q, fields="files(id)").execute().get("files", [])
    return f[0]["id"] if f else dr.files().create(body={"name": nm, "mimeType": "application/vnd.google-apps.folder", **({"parents": [parent]} if parent else {})}, fields="id").execute()["id"]
def free_bytes():
    q = dr.about().get(fields="storageQuota").execute()["storageQuota"]
    return (int(q["limit"]) - int(q["usage"])) if q.get("limit") else 10**15
def on_drive(pid):
    out, tok = {}, None
    while True:
        r = dr.files().list(q=f"'{pid}' in parents and trashed=false", fields="nextPageToken,files(name,size)", pageSize=1000, pageToken=tok).execute()
        out.update({f["name"]: int(f.get("size", 0)) for f in r.get("files", [])}); tok = r.get("nextPageToken")
        if not tok: return out
def upload(path, pid):
    size = os.path.getsize(path)
    if free_bytes() < size + (512 << 20):
        print("NO SPACE LEFT ON DRIVE - stopping before", os.path.basename(path), flush=True); sys.exit(0)
    dr.files().create(body={"name": os.path.basename(path), "parents": [pid]},
                      media_body=MediaFileUpload(path, resumable=True, chunksize=64 << 20), fields="id").execute()
    print("saved", os.path.basename(path), round(size / 1e6, 1), "MB", flush=True)
def zip_parts(name, items, pid, limit=1500 << 20):
    """items: list of (arcname, url). Download into zip parts of ~1.5 GB and upload each part."""
    part, z, cur, n = 0, None, 0, 0
    def close():
        nonlocal z
        if z:
            z.close(); upload(z.filename, pid); os.remove(z.filename); z = None
    def dl(it):
        try: return it[0], get(it[1], tries=3)
        except Exception: return it[0], None
    with cf.ThreadPoolExecutor(4) as ex:
        for arc, data in ex.map(dl, items):
            if data is None: continue
            if z is None:
                part += 1; z = zipfile.ZipFile(f"{name}_part{part:02d}.zip", "w", zipfile.ZIP_STORED); cur = 0
            z.writestr(arc, data); cur += len(data); n += 1
            if cur >= limit: close()
    close(); return n
def replace(path, pid):
    for old in dr.files().list(q=f"name='{os.path.basename(path)}' and '{pid}' in parents and trashed=false", fields="files(id)").execute().get("files", []):
        dr.files().delete(fileId=old["id"]).execute()
    upload(path, pid)

mode = sys.argv[1]
if mode == "quota":
    q = dr.about().get(fields="storageQuota").execute()["storageQuota"]
    print({k: f"{int(v)/1e9:.1f} GB" for k, v in q.items()}, flush=True)
    replace(os.path.join(os.path.dirname(os.path.abspath(__file__)), "SOUND_LICENSES.md"), folder(ROOT))
elif mode == "zenodo":
    rid, name = sys.argv[2], sys.argv[3]
    pid = folder(name, folder(ROOT)); have = on_drive(pid)
    rec = json.loads(get(f"https://zenodo.org/api/records/{rid}"))
    meta = {"title": rec["metadata"]["title"], "license": rec["metadata"].get("license"), "doi": rec.get("doi"), "url": rec["links"].get("html")}
    open("ABOUT.json", "w").write(json.dumps(meta, indent=1))
    if "ABOUT.json" not in have: upload("ABOUT.json", pid)
    for f in sorted(rec["files"], key=lambda f: f["size"]):
        if have.get(f["key"]) == f["size"]: print("already on Drive", f["key"]); continue
        fetch_to(f["links"]["self"], f["key"]); upload(f["key"], pid); os.remove(f["key"])
elif mode == "url":
    name, u = sys.argv[2], sys.argv[3]
    pid = folder(name, folder(ROOT)); fn = os.path.basename(u.split("?")[0]) or name
    if fn in on_drive(pid): print("already on Drive", fn)
    else: fetch_to(u, fn); upload(fn, pid)
elif mode == "bbc":   # BBC Sound Effects (RemArc licence: personal, educational, research use only)
    cat = sys.argv[2]; API = "https://sound-effects-api.bbcrewind.co.uk/api/sfx/search"
    def search(crit, frm, size):
        body = {"criteria": {"from": frm, "size": size, "tags": None, "categories": [cat], "durations": None, "continents": None,
                             "sortBy": None, "source": None, "recordist": None, "habitat": None, "query": None, **crit}}
        return json.loads(get(API, json.dumps(body).encode(), headers={"Content-Type": "application/json"}))
    def collect(crit):
        tot = search(crit, 0, 1).get("total", 0)
        if tot > 9900 and "durations" not in crit:      # the API only pages through 10,000 results, so split by length
            out = {}
            for lo, hi in [(0, 10), (10, 30), (30, 60), (60, 120), (120, 300), (300, 600), (600, 10**6)]:
                out.update(collect({**crit, "durations": [{"min": lo, "max": hi}]}))
            return out
        out, frm = {}, 0
        while len(out) < tot and frm * 10 < 10000:      # this API's "from" counts in steps of 10 results
            res = search(crit, frm, 500).get("results", [])
            if not res: break
            out.update({r["id"]: r for r in res}); frm += 50
        return out
    allr = collect({})
    print(cat, "found", len(allr), "of", search({}, 0, 1).get("total"), flush=True)
    pid = folder(f"bbc_{cat}", folder("bbc_sound_effects", folder(ROOT)))
    if any(n.startswith(f"bbc_{cat}_part") for n in on_drive(pid)): print("already on Drive", cat); sys.exit(0)
    with gzip.open(f"bbc_{cat}_metadata.jsonl.gz", "wt", encoding="utf-8") as g:
        for r in allr.values(): g.write(json.dumps(r, ensure_ascii=False) + "\n")
    replace(f"bbc_{cat}_metadata.jsonl.gz", pid)
    items = [(f"{i}.mp3", f"https://sound-effects-media.bbcrewind.co.uk/mp3/{i}.mp3") for i in sorted(allr)]
    print(cat, "mp3 saved", zip_parts(f"bbc_{cat}", items, pid), flush=True)
elif mode == "mixkit":   # Mixkit free sound effects (Mixkit licence: free, commercial use allowed)
    pid = folder("mixkit", folder(ROOT))
    if any(n.startswith("mixkit_part") for n in on_drive(pid)): print("already on Drive"); sys.exit(0)
    html = get("https://mixkit.co/free-sound-effects/").decode("utf-8", "ignore")
    cats = sorted(set(re.findall(r'/free-sound-effects/([a-z0-9-]+)/', html)))
    rows = {}
    for ct in cats:
        for page in range(1, 60):
            try: h = get(f"https://mixkit.co/free-sound-effects/{ct}/?page={page}", tries=2).decode("utf-8", "ignore")
            except Exception: break
            new = [i for i in re.findall(r'sfx/(\d+)/\1-preview\.mp3', h) if i not in rows]
            for i in new: rows[i] = {"id": i, "category": ct}
            if not new: break
            time.sleep(0.5)
    print("mixkit sounds", len(rows), "in", len(cats), "categories", flush=True)
    with gzip.open("mixkit_metadata.jsonl.gz", "wt", encoding="utf-8") as g:
        for r in rows.values(): g.write(json.dumps(r) + "\n")
    replace("mixkit_metadata.jsonl.gz", pid)
    items = [(f"{r['category']}/{i}.mp3", f"https://assets.mixkit.co/active_storage/sfx/{i}/{i}-preview.mp3") for i, r in sorted(rows.items(), key=lambda x: int(x[0]))]
    print("mixkit mp3 saved", zip_parts("mixkit", items, pid), flush=True)
elif mode == "archive":   # archive.org items (Sonniss GDC bundles etc.)
    aid, name = sys.argv[2], sys.argv[3]
    pid = folder(name, folder(ROOT)); have = on_drive(pid)
    meta = json.loads(get(f"https://archive.org/metadata/{aid}"))
    files = [f for f in meta.get("files", []) if f["name"].endswith((".wav", ".flac", ".mp3", ".ogg", ".aif", ".aiff"))]
    print(name, len(files), "audio files", round(sum(int(f.get("size", 0)) for f in files) / 1e9, 2), "GB", flush=True)
    # Group by top-level directory (each contributor's pack) and upload as zip parts
    groups = {}
    for f in files:
        top = f["name"].split("/")[0] if "/" in f["name"] else "_root"
        groups.setdefault(top, []).append(f)
    done, total = 0, len(files)
    for gname in sorted(groups):
        items = [(f["name"], f"https://archive.org/download/{aid}/{urllib.request.quote(f['name'])}") for f in groups[gname]]
        tag = re.sub(r"[^a-zA-Z0-9_-]", "_", gname)[:60]
        n = zip_parts(f"{name}_{tag}", items, pid)
        done += n; print(f"  {gname}: {n} files  ({done}/{total})", flush=True)
    print(name, "done", done, "of", total, "files", flush=True)
elif mode == "pixabay":   # Pixabay sound effects via API (Pixabay licence: free, commercial use, no attribution required)
    key = os.environ["PIXABAY_API_KEY"]
    pid = folder("pixabay", folder(ROOT))
    if any(n.startswith("pixabay_part") for n in on_drive(pid)): print("already on Drive"); sys.exit(0)
    # Pixabay audio search API - collect all pages
    rows, page = [], 1
    while True:
        d = json.loads(get(f"https://pixabay.com/api/?key={key}&per_page=200&page={page}&safesearch=true&editors_choice=false&order=latest&audio_type=sfx", tries=3))
        hits = d.get("hits", [])
        if not hits: break
        for h in hits:
            audio_url = h.get("audio", {}).get("mp3", {}).get("url") or h.get("audio", {}).get("128kbps", {}).get("url") or h.get("previewURL", "")
            if audio_url:
                rows.append({"id": h["id"], "tags": h.get("tags", ""), "url": audio_url, "duration": h.get("duration")})
        page += 1
        if page * 200 >= d.get("totalHits", d.get("total", 0)): break
        time.sleep(0.3)
    # Fallback: scrape categories if API returns nothing (API may not support audio yet)
    if not rows:
        print("API returned 0 audio hits, trying web scrape", flush=True)
        html = get("https://pixabay.com/sound-effects/").decode("utf-8", "ignore")
        cats = sorted(set(re.findall(r'/sound-effects/([a-z0-9-]+)/', html)))
        for ct in cats:
            for pg in range(1, 40):
                try: h = get(f"https://pixabay.com/sound-effects/search/{ct}/?pagi={pg}", tries=2).decode("utf-8", "ignore")
                except Exception: break
                ids = re.findall(r'/sound-effects/[^/]+-(\d+)/', h); new = [i for i in ids if i not in {str(r["id"]) for r in rows}]
                if not new: break
                for i in new: rows.append({"id": int(i), "tags": ct, "url": f"https://pixabay.com/sound-effects/download/sound-effect-{i}.mp3", "duration": None})
                time.sleep(0.5)
    print("pixabay sounds", len(rows), flush=True)
    with gzip.open("pixabay_metadata.jsonl.gz", "wt", encoding="utf-8") as g:
        for r in rows: g.write(json.dumps(r) + "\n")
    replace("pixabay_metadata.jsonl.gz", pid)
    items = [(f"{r['tags'].split(',')[0].strip()}/{r['id']}.mp3", r["url"]) for r in rows if r["url"]]
    print("pixabay mp3 saved", zip_parts("pixabay", items, pid), flush=True)
elif mode == "mendeley":   # Mendeley Data datasets (zip download)
    did, name = sys.argv[2], sys.argv[3]
    pid = folder(name, folder(ROOT)); have = on_drive(pid)
    fn = f"{did}.zip"
    if fn in have: print("already on Drive", fn); sys.exit(0)
    # Mendeley provides a zip download for entire datasets
    fetch_to(f"https://data.mendeley.com/datasets/{did}/1/files/download", fn)
    upload(fn, pid); os.remove(fn)
    print(name, "saved", flush=True)
elif mode == "freesound_search":   # Freesound via API (needs FREESOUND_API_KEY env)
    key = os.environ["FREESOUND_API_KEY"]
    query = sys.argv[2] if len(sys.argv) > 2 else ""
    pid = folder("freesound", folder(ROOT)); have = on_drive(pid)
    # Search and download CC0 sounds
    page, rows = 1, []
    while True:
        d = json.loads(get(f"https://freesound.org/apiv2/search/text/?query={urllib.request.quote(query)}&filter=license:%22Creative+Commons+0%22&fields=id,name,tags,previews,duration,license&page_size=150&page={page}&token={key}"))
        for r in d.get("results", []):
            mp3 = r.get("previews", {}).get("preview-hq-mp3", r.get("previews", {}).get("preview-lq-mp3", ""))
            if mp3: rows.append({"id": r["id"], "name": r["name"], "tags": r.get("tags", []), "url": mp3, "license": r.get("license"), "duration": r.get("duration")})
        if not d.get("next"): break
        page += 1; time.sleep(0.5)
    print(f"freesound CC0 '{query}'", len(rows), "sounds", flush=True)
    tag = re.sub(r"[^a-z0-9]", "_", query.lower())[:30] or "all"
    with gzip.open(f"freesound_{tag}_metadata.jsonl.gz", "wt", encoding="utf-8") as g:
        for r in rows: g.write(json.dumps(r, ensure_ascii=False) + "\n")
    replace(f"freesound_{tag}_metadata.jsonl.gz", pid)
    items = [(f"{r['id']}_{r['name'][:40]}.mp3", r["url"]) for r in rows]
    print("freesound saved", zip_parts(f"freesound_{tag}", items, pid), flush=True)
