"""Read ONLY the text column of a public Hugging Face speech dataset (no audio) and save it to the owner's PRIVATE Google Drive
(folder "Kulfi Phrase Bank/conversation/<lang>"). Nothing is kept on GitHub; the log prints only counts.
Usage: python phrase_text.py <dataset_id> <lang>"""
import gzip, json, os, sys, time
import pyarrow.parquet as pq
from huggingface_hub import HfFileSystem
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
ds, lang = sys.argv[1], sys.argv[2]
fs = HfFileSystem()
files = sorted(fs.glob(f"datasets/{ds}/**/*.parquet"))
print("files", len(files), flush=True)
name = ds.split("/")[-1] + ".jsonl.gz"
n = 0
with gzip.open(name, "wt", encoding="utf-8") as g:
    for i, f in enumerate(files):
        rows = []
        for attempt in range(4):
            try:
                pf = pq.ParquetFile(f, filesystem=fs)
                cols = [c for c in pf.schema_arrow.names if c not in ("audio",)]
                rows = pf.read(columns=cols).to_pylist()
                break
            except Exception as e:
                print("retry file", i, type(e).__name__, flush=True); time.sleep(30 * (attempt + 1))
        split = "test" if "/test" in f else "train"
        for r in rows:
            r = {k: v for k, v in r.items() if isinstance(v, (str, int, float))}
            if any(isinstance(v, str) and len(v) > 1 for v in r.values()):
                r["split"] = split; g.write(json.dumps(r, ensure_ascii=False) + "\n"); n += 1
        print("file", i + 1, "of", len(files), "lines so far", n, flush=True)
c = Credentials.from_authorized_user_info(json.loads(os.environ["DRIVE_TOKEN"]))
if not c.valid: c.refresh(Request())
dr = build("drive", "v3", credentials=c, cache_discovery=False)
def folder(nm, parent=None):
    q = f"name='{nm}' and mimeType='application/vnd.google-apps.folder' and trashed=false" + (f" and '{parent}' in parents" if parent else "")
    f = dr.files().list(q=q, fields="files(id)").execute().get("files", [])
    return f[0]["id"] if f else dr.files().create(body={"name": nm, "mimeType": "application/vnd.google-apps.folder", **({"parents": [parent]} if parent else {})}, fields="id").execute()["id"]
pid = folder(lang, folder("conversation", folder("Kulfi Phrase Bank")))
for old in dr.files().list(q=f"name='{name}' and '{pid}' in parents and trashed=false", fields="files(id)").execute().get("files", []):
    dr.files().delete(fileId=old["id"]).execute()
dr.files().create(body={"name": name, "parents": [pid]}, media_body=MediaFileUpload(name, mimetype="application/gzip", resumable=True), fields="id").execute()
print("DONE", n, "lines saved to private Google Drive", flush=True)
