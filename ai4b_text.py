"""Read ONLY text columns (no audio) of AI4Bharat IndicVoices / Rasa for one language and save to the owner's PRIVATE Google Drive
("Kulfi Phrase Bank/ai4bharat/<dataset>/<language>.jsonl.gz"). Needs HF_TOKEN (owner's account already has access). Log prints counts only.
Usage: python ai4b_text.py <IndicVoices|Rasa> <folder name e.g. telugu / Telugu>"""
import gzip, json, os, sys, time
import pyarrow.parquet as pq
from huggingface_hub import HfFileSystem
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
dsname, folder = sys.argv[1], sys.argv[2]
WANT = {"IndicVoices": ["text", "verbatim", "scenario", "task_name", "gender", "age_group", "state", "district"],
        "Rasa": ["text", "style", "gender", "language"]}[dsname]
fs = HfFileSystem(token=os.environ["HF_TOKEN"])
files = sorted(fs.glob(f"datasets/ai4bharat/{dsname}/{folder}/*.parquet"))
print(dsname, folder, "files", len(files), flush=True)
out = f"{folder}.jsonl.gz"; n = 0
with gzip.open(out, "wt", encoding="utf-8") as g:
    for i, f in enumerate(files):
        rows = []
        for attempt in range(4):
            try:
                pf = pq.ParquetFile(f, filesystem=fs)
                rows = pf.read(columns=[c for c in WANT if c in pf.schema_arrow.names]).to_pylist(); break
            except Exception as e:
                print("retry", i, type(e).__name__, flush=True); time.sleep(30 * (attempt + 1))
        for r in rows:
            if r.get("text") or r.get("verbatim"):
                r["split"] = f.split("/")[-1].split("-")[0]; g.write(json.dumps(r, ensure_ascii=False) + "\n"); n += 1
        if (i + 1) % 10 == 0: print("file", i + 1, "of", len(files), "lines", n, flush=True)
c = Credentials.from_authorized_user_info(json.loads(os.environ["DRIVE_TOKEN"]))
if not c.valid: c.refresh(Request())
dr = build("drive", "v3", credentials=c, cache_discovery=False)
def fold(nm, parent=None):
    q = f"name='{nm}' and mimeType='application/vnd.google-apps.folder' and trashed=false" + (f" and '{parent}' in parents" if parent else "")
    f = dr.files().list(q=q, fields="files(id)").execute().get("files", [])
    return f[0]["id"] if f else dr.files().create(body={"name": nm, "mimeType": "application/vnd.google-apps.folder", **({"parents": [parent]} if parent else {})}, fields="id").execute()["id"]
pid = fold(dsname, fold("ai4bharat", fold("Kulfi Phrase Bank")))
for old in dr.files().list(q=f"name='{out}' and '{pid}' in parents and trashed=false", fields="files(id)").execute().get("files", []):
    dr.files().delete(fileId=old["id"]).execute()
dr.files().create(body={"name": out, "parents": [pid]}, media_body=MediaFileUpload(out, mimetype="application/gzip", resumable=True), fields="id").execute()
print("DONE", dsname, folder, n, "lines saved to private Google Drive", flush=True)
