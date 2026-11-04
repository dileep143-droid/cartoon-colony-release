# BuBu TV song Shorts (owner 4 Nov 2026): full song video (Kaggle output) -> 9:16 Short of the funniest part -> Google Drive "BuBu TV Shorts/<slug>".
#   python song_short.py <slug> <code>
# Cut points per language: data/songs/<slug>/shorts.json (Verse 2 conflict + Chorus 2, 29-47 s). Layout: blurred copy fills 1080x1920, the 16:9 video sits
# in the middle scaled to full width. Never downloads to the laptop; nothing is uploaded to YouTube here (the daily timer does that).
import json, os, re, subprocess, sys
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
slug, code = sys.argv[1:3]
D = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "songs", slug)
cut = json.load(open(os.path.join(D, "shorts.json")))[code]; src = json.load(open(os.path.join(D, "release.json"), encoding="utf-8"))["files"][code]
name = cut["file"].replace(".mp4", "_short.mp4")
c = Credentials.from_authorized_user_info(json.loads(os.environ["DRIVE_TOKEN"]))
if not c.valid: c.refresh(Request())
dr = build("drive", "v3", credentials=c, cache_discovery=False)
def folder(nm, parent=None):
    q = f"name='{nm}' and mimeType='application/vnd.google-apps.folder' and trashed=false" + (f" and '{parent}' in parents" if parent else "")
    f = dr.files().list(q=q, fields="files(id)").execute().get("files", [])
    return f[0]["id"] if f else dr.files().create(body={"name": nm, "mimeType": "application/vnd.google-apps.folder", **({"parents": [parent]} if parent else {})}, fields="id").execute()["id"]
pid = folder(slug, folder("BuBu TV Shorts"))
if dr.files().list(q=f"name='{name}' and '{pid}' in parents and trashed=false", fields="files(id)").execute().get("files"):
    print(f"RESULT {slug} {code} ALREADY_IN_DRIVE"); sys.exit(0)
env = dict(os.environ, KAGGLE_API_TOKEN=os.environ[f"KAGGLE_KEY{src['key']}"], PYTHONUTF8="1"); os.makedirs("dl", exist_ok=True)
r = subprocess.run(["kaggle", "kernels", "output", src["kernel"], "-p", "dl", "--file-pattern", "^" + re.escape(src["file"]) + "$"], env=env, capture_output=True, text=True)
full = os.path.join("dl", src["file"])
if not os.path.exists(full): sys.exit("download failed: " + (r.stdout + r.stderr)[-300:])
vf = ("[0:v]split[a][b];[a]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,boxblur=30:3,eq=brightness=-0.08[bg];"
      "[b]scale=1350:-2,crop=1080:ih[fg];[bg][fg]overlay=(W-w)/2:(H-h)/2,fps=30,format=yuv420p[v]")
dur = cut["end"] - cut["start"]
cmd = ["ffmpeg", "-y", "-v", "error", "-ss", str(cut["start"]), "-t", f"{dur:.2f}", "-i", full, "-filter_complex", vf, "-map", "[v]", "-map", "0:a",
       "-af", f"afade=t=in:d=0.3,afade=t=out:st={max(0, dur - 0.8):.2f}:d=0.8", "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-c:a", "aac", "-b:a", "160k", name]
subprocess.run(cmd, check=True)
up = dr.files().create(body={"name": name, "parents": [pid]}, media_body=MediaFileUpload(name, chunksize=32 * 2**20, resumable=True), fields="id,size"); resp = None
while resp is None: _, resp = up.next_chunk()
print(f"RESULT {slug} {code} SHORT_IN_DRIVE {round(dur,1)}s {int(resp['size'])//1_000_000}MB")
