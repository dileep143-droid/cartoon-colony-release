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
dur = cut["end"] - cut["start"]
# 4 Nov owner "make it zoom": full-screen 9:16 smart crop. Each scene (clip) has its own crop centre x (Claude/Gemini looked at its start picture);
# the source is scaled to 1920 high (3413 wide) and a 1080-wide window is cut around that centre, scene by scene.
parts = []; segs = cut.get("segs") or [[0, dur, 0.5]]
for i, (s0, s1, x) in enumerate(segs):
    cx = int(min(max(x * 3413 - 540, 0), 3413 - 1080))
    parts.append(f"[0:v]trim=start={s0:.3f}:end={s1:.3f},setpts=PTS-STARTPTS,scale=-2:1920,crop=1080:1920:{cx}:0,setsar=1,fps=30[p{i}]")
vf = ";".join(parts) + ";" + "".join(f"[p{i}]" for i in range(len(segs))) + f"concat=n={len(segs)}:v=1:a=0,format=yuv420p[v]"
cmd = ["ffmpeg", "-y", "-v", "error", "-ss", str(cut["start"]), "-t", f"{dur:.2f}", "-i", full, "-filter_complex", vf, "-map", "[v]", "-map", "0:a",
       "-af", f"afade=t=in:d=0.3,afade=t=out:st={max(0, dur - 0.8):.2f}:d=0.8", "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-c:a", "aac", "-b:a", "160k", name]
subprocess.run(cmd, check=True)
up = dr.files().create(body={"name": name, "parents": [pid]}, media_body=MediaFileUpload(name, chunksize=32 * 2**20, resumable=True), fields="id,size"); resp = None
tries = 0   # 4 Nov: GitHub runners sometimes get SSL EOF during big Drive uploads -> resume the same upload (resumable) up to 8 times
while resp is None:
    try: _, resp = up.next_chunk()
    except Exception as e:
        tries += 1
        if tries > 8: raise
        print('upload retry', tries, str(e)[-80:], flush=True); import time as _t; _t.sleep(10 * tries)
print(f"RESULT {slug} {code} SHORT_IN_DRIVE {round(dur,1)}s {int(resp['size'])//1_000_000}MB")
