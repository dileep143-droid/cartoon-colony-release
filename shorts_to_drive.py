# 18 Nov 2026 owner: "Only songs shorts ... create them in git" -> remake the song Shorts that went straight to YouTube (song_daily.py cut them
# on the fly, no file was kept) and save them to Google Drive: BuBu TV Shorts/<Language>/<slug>_<lang>_p<part>_short.mp4.
# The cut is IDENTICAL to song_daily.py (same start/length, zoom to 1080x1920, logo, travelling see-through BUBU TV, fades).
#   python shorts_to_drive.py hi S14_moon:1,S15_rain:1,...      Files already in the Drive folder are skipped. No YouTube calls.
import io, json, os, subprocess, sys, time
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload, MediaIoBaseDownload
code = sys.argv[1]; jobs = [(x.split(":")[0], int(x.split(":")[1])) for x in sys.argv[2].split(",") if x.strip()]
NAME = {"hi": "hindi"}; LANG = {"hi": "Hindi"}
c = Credentials.from_authorized_user_info(json.loads(os.environ["DRIVE_TOKEN"]))
if not c.valid: c.refresh(Request())
dr = build("drive", "v3", credentials=c, cache_discovery=False)
def retry(fn, n=5):
    for k in range(n):
        try: return fn()
        except Exception as e:
            if k == n - 1: raise
            print("retry", k + 1, str(e)[-120:], flush=True); time.sleep(15 * (k + 1))
def folder(name, parent=None):
    q = f"name='{name}' and mimeType='application/vnd.google-apps.folder' and trashed=false" + (f" and '{parent}' in parents" if parent else "")
    f = retry(lambda: dr.files().list(q=q, fields="files(id)").execute()).get("files", [])
    if f: return f[0]["id"]
    body = {"name": name, "mimeType": "application/vnd.google-apps.folder", **({"parents": [parent]} if parent else {})}
    return retry(lambda: dr.files().create(body=body, fields="id").execute())["id"]
def drive_file(slug, name):
    for f in retry(lambda: dr.files().list(q=f"name='{name}' and trashed=false", fields="files(id,parents)").execute()).get("files", []):
        if retry(lambda: dr.files().get(fileId=f["parents"][0], fields="name").execute())["name"] == slug: return f["id"]
    return None
OUT = folder(LANG[code], folder("BuBu TV Shorts")); print("RESULT folder ready", flush=True)
have = {f["name"]: f["id"] for f in retry(lambda: dr.files().list(q=f"'{OUT}' in parents and trashed=false", fields="files(id,name,size)", pageSize=200).execute()).get("files", [])}
res = {}
for slug, part in jobs:
    path = f"{slug}_{code}_p{part}_short.mp4"
    if path in have: res[path] = have[path]; print(f"RESULT {slug} p{part} ALREADY {have[path]}", flush=True); continue
    fid = drive_file(slug, f"{slug[:3]}_{NAME[code]}.mp4")
    if not fid: print(f"RESULT {slug} p{part} NO FULL SONG IN DRIVE", flush=True); continue
    full = f"{slug}_{code}_full.mp4"; fh = io.FileIO(full, "wb"); dl = MediaIoBaseDownload(fh, dr.files().get_media(fileId=fid), chunksize=32 * 2**20); ok = False
    while not ok: _, ok = dl.next_chunk()
    fh.close()
    # ---- identical to song_daily.py (Shorts part) ----
    try: dur = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", full], capture_output=True, text=True).stdout.strip())
    except Exception: dur = 120.0
    L = min(42.0, max(20.0, dur / 2 - 4)); st = 6.0 if part == 1 else max(6.0, dur / 2)
    if st + L > dur - 1: L = max(15.0, dur - 1 - st)
    FONT = "data/long/fonts/LilitaOne-Regular.ttf"; LOGO = "data/long/logo.png"
    ph = sum(map(ord, slug + code + str(part))) * 97 % 3000; ph2 = sum(map(ord, slug + code + str(part))) * 53 % 1800
    name = (f",drawtext=fontfile={FONT}:text='BUBU TV':fontcolor=white@0.5:fontsize=h*0.035:x='abs(mod(t*61+{ph}\\,2*(w-tw-40))-(w-tw-40))+20'"
            f":y='abs(mod(t*37+{ph2}\\,2*(h-th-40))-(h-th-40))+20':shadowcolor=black@0.3:shadowx=2:shadowy=2") if os.path.exists(FONT) else ""
    fade = f"fade=t=in:st=0:d=0.3,fade=t=out:st={L - 0.6:.2f}:d=0.6"
    if os.path.exists(LOGO):
        ins = ["-i", full, "-i", LOGO]; vf = (f"[0:v]scale=-2:1920,crop=1080:1920,setsar=1{name}[z];[1:v]scale=170:170,format=rgba,colorchannelmixer=aa=0.92[l];"
                                             f"[z][l]overlay=W-w-40:60,{fade},format=yuv420p[v]")
    else:
        ins = ["-i", full]; vf = f"[0:v]scale=-2:1920,crop=1080:1920,setsar=1{name},{fade},format=yuv420p[v]"
    r = subprocess.run(["ffmpeg", "-y", "-v", "error", "-ss", f"{st:.2f}", "-t", f"{L:.2f}"] + ins + ["-filter_complex", vf, "-map", "[v]", "-map", "0:a",
                        "-af", f"afade=t=in:st=0:d=0.3,afade=t=out:st={L - 0.6:.2f}:d=0.6", "-c:v", "libx264", "-crf", "20", "-preset", "veryfast", "-c:a", "aac", "-b:a", "160k", path], capture_output=True, text=True)
    os.remove(full)
    if r.returncode or not os.path.exists(path): print(f"RESULT {slug} p{part} CUT FAILED {r.stderr[-200:]}", flush=True); continue
    # ---- upload ----
    up = retry(lambda: dr.files().create(body={"name": path, "parents": [OUT]}, media_body=MediaFileUpload(path, mimetype="video/mp4", resumable=True), fields="id,size").execute())
    res[path] = up["id"]; print(f"RESULT {slug} p{part} UPLOADED {up['id']} {int(up['size'])//1000} KB {L:.0f}s", flush=True); os.remove(path)
print("RESULT JSON " + json.dumps(res))
print(f"RESULT done {len(res)} of {len(jobs)}")
