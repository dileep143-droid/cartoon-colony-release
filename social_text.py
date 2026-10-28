"""Collect open colloquial text for all our languages and save it to the owner's PRIVATE Google Drive
("Kulfi Phrase Bank/social/<source>/<file>"). Nothing is kept on GitHub; the log prints only counts.
Usage:  python social_text.py cv | tatoeba | reddit <subreddit> <lang> | hf <dataset_id>"""
import bz2, csv, gzip, io, json, os, sys, time, urllib.request, urllib.parse
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
UA = {"User-Agent": "kulfi-phrase-bank/0.1 (research; contact via GitHub)"}
def get(u, tries=5):
    for i in range(tries):
        try:
            return urllib.request.urlopen(urllib.request.Request(u, headers=UA), timeout=120).read()
        except Exception as e:
            last = e; time.sleep(10 * (i + 1))
    raise last
def drive_save(path, sub):
    c = Credentials.from_authorized_user_info(json.loads(os.environ["DRIVE_TOKEN"]))
    if not c.valid: c.refresh(Request())
    dr = build("drive", "v3", credentials=c, cache_discovery=False)
    def folder(nm, parent=None):
        q = f"name='{nm}' and mimeType='application/vnd.google-apps.folder' and trashed=false" + (f" and '{parent}' in parents" if parent else "")
        f = dr.files().list(q=q, fields="files(id)").execute().get("files", [])
        return f[0]["id"] if f else dr.files().create(body={"name": nm, "mimeType": "application/vnd.google-apps.folder", **({"parents": [parent]} if parent else {})}, fields="id").execute()["id"]
    pid = folder(sub, folder("social", folder("Kulfi Phrase Bank")))
    name = os.path.basename(path)
    for old in dr.files().list(q=f"name='{name}' and '{pid}' in parents and trashed=false", fields="files(id)").execute().get("files", []):
        dr.files().delete(fileId=old["id"]).execute()
    dr.files().create(body={"name": name, "parents": [pid]}, media_body=MediaFileUpload(path, mimetype="application/gzip", resumable=True), fields="id").execute()
def write(name, rows):
    path = name + ".jsonl.gz"
    with gzip.open(path, "wt", encoding="utf-8") as g:
        for r in rows: g.write(json.dumps(r, ensure_ascii=False) + "\n")
    return path
mode = sys.argv[1]
if mode == "cv":   # Common Voice sentence-collector (CC0)
    CODES = {"te": "te", "hi": "hi", "ta": "ta", "kn": "kn", "ml": "ml", "bn": "bn", "mr": "mr", "pa": "pa-IN", "or": "or", "as": "as", "ur": "ur"}
    for lang, code in CODES.items():
        try:
            t = get(f"https://raw.githubusercontent.com/common-voice/common-voice/main/server/data/{code}/sentence-collector.txt").decode("utf-8", "ignore")
        except Exception as e:
            print(lang, "no file", type(e).__name__); continue
        rows = [{"text": l.strip(), "lang": lang, "source": "common_voice"} for l in t.splitlines() if l.strip()]
        drive_save(write(f"commonvoice_{lang}", rows), "common_voice"); print(lang, len(rows), "sentences", flush=True)
elif mode == "tatoeba":   # Tatoeba per-language exports (CC-BY 2.0 FR)
    CODES = {"te": "tel", "hi": "hin", "ta": "tam", "kn": "kan", "ml": "mal", "bn": "ben", "mr": "mar", "gu": "guj", "pa": "pan", "or": "ory", "as": "asm", "ur": "urd"}
    for lang, code in CODES.items():
        try:
            raw = bz2.decompress(get(f"https://downloads.tatoeba.org/exports/per_language/{code}/{code}_sentences.tsv.bz2")).decode("utf-8", "ignore")
        except Exception as e:
            print(lang, "no export", type(e).__name__); continue
        rows = [{"text": p[2], "lang": lang, "source": "tatoeba", "id": p[0]} for p in (l.split("\t") for l in raw.splitlines()) if len(p) >= 3]
        drive_save(write(f"tatoeba_{lang}", rows), "tatoeba"); print(lang, len(rows), "sentences", flush=True)
elif mode == "reddit":   # Reddit comments through the Arctic Shift archive API (inspiration only)
    sub, lang = sys.argv[2], sys.argv[3]
    MAX = int(os.environ.get("REDDIT_MAX", "30000"))
    rows, before = [], None
    while len(rows) < MAX:
        q = {"subreddit": sub, "limit": 100, "sort": "desc"}
        if before: q["before"] = before
        try:
            d = json.loads(get("https://arctic-shift.photon-reddit.com/api/comments/search?" + urllib.parse.urlencode(q)))
        except Exception as e:
            print("stop", type(e).__name__); break
        data = d.get("data", [])
        if not data: break
        for c in data:
            b = (c.get("body") or "").strip()
            if b and b not in ("[deleted]", "[removed]"):
                rows.append({"text": b, "lang": lang, "source": "reddit", "subreddit": sub, "created_utc": c.get("created_utc"), "score": c.get("score")})
        before = min(int(c["created_utc"]) for c in data)
        time.sleep(1.0)
    drive_save(write(f"reddit_{sub}", rows), "reddit"); print(sub, lang, len(rows), "comments", flush=True)
elif mode == "hf":   # small open Hugging Face text datasets (all non-audio columns)
    import pyarrow.parquet as pq
    from huggingface_hub import HfFileSystem
    ds = sys.argv[2]; fs = HfFileSystem(); rows = []
    for f in fs.glob(f"datasets/{ds}/**"):
        if f.endswith(".parquet"):
            for r in pq.read_table(f, filesystem=fs).to_pylist():
                rows.append({**{k: v for k, v in r.items() if isinstance(v, (str, int, float))}, "file": f.split(ds + "/")[-1]})
        elif f.endswith(".csv"):
            with fs.open(f, "rb") as h:
                for r in csv.DictReader(io.StringIO(h.read().decode("utf-8", "ignore"))):
                    rows.append({**r, "file": f.split(ds + "/")[-1]})
    drive_save(write("hf_" + ds.replace("/", "__"), rows), "hf_datasets"); print(ds, len(rows), "rows", flush=True)
print("DONE", mode, flush=True)
