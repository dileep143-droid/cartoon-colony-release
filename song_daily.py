# BuBu TV daily song timer (owner 3 Nov 2026): Google Drive -> YouTube, 5 new songs per channel per day, going public at 07:00 10:00 13:00 16:00 19:00 IST.
#   python song_daily.py <code>      (one language channel; GitHub matrix runs all 20)
# Queue = data/songs/queue.json (only songs Claude checked). A song counts as done on a channel when a video with its exact title exists there,
# so re-runs never duplicate. Quota/upload errors stop this channel for today; the next day continues where it stopped.
import datetime, io, json, os, sys, time
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload, MediaIoBaseDownload
code = sys.argv[1]; SHORTS_PER_DAY = 0
# 10 Nov owner: 2-minute songs again. 8 verified channels (long videos + own thumbnails): 2 a day. 12 others (no long videos): 4 a day. No Shorts. 100 uploads/day shared.
VERIFIED = {"hi", "te", "ta", "kn", "mr", "bn", "en", "ur"}
PER_DAY = int(os.environ.get("SONGS_PER_DAY") or (2 if code in VERIFIED else 4)); SLOTS_IST = [14, 18] if code in VERIFIED else [10, 13, 16, 19]   # away from the long videos (06:00 + hourly)
PER_DAY = min(PER_DAY, len(SLOTS_IST))
NAME = {"hi": "hindi", "te": "telugu", "ta": "tamil", "kn": "kannada", "ml": "malayalam", "mr": "marathi", "bn": "bengali", "gu": "gujarati", "pa": "punjabi", "or": "odia",
        "as": "assamese", "en": "english", "ne": "nepali", "ur": "urdu", "sd": "sindhi", "mai": "maithili", "hry": "haryanvi", "ks": "kashmiri", "mni": "manipuri", "bho": "bhojpuri"}
NEW = {"ne", "ur", "sd", "mai", "hry", "ks", "mni", "bho"}; YT_LANG = {"ne": "ne", "ur": "ur"}
D = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "songs")
queue = json.load(open(os.path.join(D, "queue.json")))["songs"]
def creds(env):
    c = Credentials.from_authorized_user_info(json.loads(os.environ[env]))
    if not c.valid: c.refresh(Request())
    return c
def retry(fn, n=5):
    for k in range(n):
        try: return fn()
        except Exception as e:
            if "quota" in str(e).lower() or k == n - 1: raise
            print("retry", k + 1, str(e)[-120:], flush=True); time.sleep(20 * (k + 1))
yt = build("youtube", "v3", credentials=creds("YT_TOKEN"), cache_discovery=False)
dr = build("drive", "v3", credentials=creds("DRIVE_TOKEN"), cache_discovery=False)
up = retry(lambda: yt.channels().list(part="contentDetails", mine=True).execute())["items"][0]["contentDetails"]["relatedPlaylists"]["uploads"]
have, tok = set(), None
while True:                                               # every title already on the channel (public, private or scheduled)
    r = retry(lambda: yt.playlistItems().list(part="snippet", playlistId=up, maxResults=50, pageToken=tok).execute())
    have |= {i["snippet"]["title"].strip() for i in r["items"]}; tok = r.get("nextPageToken")
    if not tok or len(have) > 400: break
now = datetime.datetime.now(datetime.timezone.utc); ist = datetime.timezone(datetime.timedelta(hours=5, minutes=30))
today = now.astimezone(ist).date()
slots = [datetime.datetime(today.year, today.month, today.day, h, 0, tzinfo=ist) for h in SLOTS_IST]
slots = [max(s, now + datetime.timedelta(minutes=40)) for s in slots]       # GitHub timers can start late -> never schedule in the past
def drive_file(slug, name):
    q = f"name='{name}' and trashed=false"
    for f in retry(lambda: dr.files().list(q=q, fields="files(id,parents)").execute()).get("files", []):
        par = retry(lambda: dr.files().get(fileId=f["parents"][0], fields="name").execute())["name"]
        if par == slug: return f["id"]
    return None
done = 0
for slug in queue:
    if done >= PER_DAY: break
    mp = os.path.join(D, slug, f"meta_{code}.json")
    if not os.path.exists(mp): continue
    meta = json.load(open(mp, encoding="utf-8")); title = meta["title"][:100].strip()
    if title in have: continue
    fname = f"{slug[:3]}_{NAME[code]}.mp4"; path = f"{slug}_{code}.mp4"
    fid = drive_file(slug, fname)
    if fid:
        fh = io.FileIO(path, "wb"); dl = MediaIoBaseDownload(fh, dr.files().get_media(fileId=fid), chunksize=64 * 2**20); ok = False
        while not ok: _, ok = dl.next_chunk()
        fh.close()
    else:   # 4 Nov: owner's Drive is full (15 GB) -> fall back to the song's Kaggle output (release.json says which kernel/key)
        import subprocess, re as _re
        src = json.load(open(os.path.join(D, slug, "release.json"), encoding="utf-8"))["files"].get(code)
        if not src: print(f"RESULT {code} {slug} NO_SOURCE"); continue
        env = dict(os.environ, KAGGLE_API_TOKEN=os.environ.get(f"KAGGLE_KEY{src['key']}", ""), PYTHONUTF8="1"); os.makedirs("dl", exist_ok=True)
        subprocess.run(["kaggle", "kernels", "output", src["kernel"], "-p", "dl", "--file-pattern", "^" + _re.escape(src["file"]) + "$"], env=env, capture_output=True, text=True)
        if not os.path.exists(os.path.join("dl", src["file"])): print(f"RESULT {code} {slug} NOT_IN_DRIVE_OR_KAGGLE"); continue
        os.replace(os.path.join("dl", src["file"]), path); print(f"{slug} {code} taken from Kaggle (Drive copy missing)", flush=True)
    FONT = "data/long/fonts/LilitaOne-Regular.ttf"   # relative: the workflow runs in the repo folder (a Windows C: path breaks drawtext)
    if os.path.exists(FONT):   # 9/10 Nov owner: see-through "BUBU TV" travelling slowly across the screen, like the long videos
        import subprocess
        ph = sum(map(ord, slug + code)) * 97 % 3000; ph2 = sum(map(ord, slug + code)) * 53 % 1800
        vf = (f"drawtext=fontfile={FONT}:text='BUBU TV':fontcolor=white@0.5:fontsize=h*0.05:"
              f"x='abs(mod(t*61+{ph}\\,2*(w-tw-40))-(w-tw-40))+20':y='abs(mod(t*37+{ph2}\\,2*(h-th-40))-(h-th-40))+20':shadowcolor=black@0.3:shadowx=2:shadowy=2")
        w = subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", path, "-vf", vf, "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p", "-c:a", "copy", "wm_" + path], capture_output=True, text=True)
        if w.returncode == 0 and os.path.getsize("wm_" + path) > 500_000: os.replace("wm_" + path, path); print(f"{slug} {code} channel name added", flush=True)
        else: print(f"{slug} {code} WATERMARK FAILED {w.stderr[-200:]} - uploading without", flush=True)
    if os.environ.get("DRY") == "1":   # test mode: everything except the upload
        print(f"RESULT {code} {slug} DRY would schedule at {slots[done].astimezone(ist):%H:%M} IST, file {os.path.getsize(path)//1_000_000} MB", flush=True); done += 1; have.add(title); os.remove(path); continue
    pub = slots[done].astimezone(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    sn = {"title": title, "description": meta["description"][:5000], "tags": meta["tags"][:30], "categoryId": "27"}
    yl = code if code not in NEW else YT_LANG.get(code)
    if yl: sn.update({"defaultLanguage": yl, "defaultAudioLanguage": yl})
    body = {"snippet": sn, "status": {"privacyStatus": "private", "publishAt": pub, "selfDeclaredMadeForKids": True, "embeddable": True, "containsSyntheticMedia": True}}
    try:
        req = yt.videos().insert(part="snippet,status", body=body, media_body=MediaFileUpload(path, chunksize=16 * 2**20, resumable=True)); res = None
        while res is None: _, res = req.next_chunk()
    except Exception as e:
        print(f"RESULT {code} {slug} STOPPED {str(e)[-200:]}"); break             # quota or upload limit -> continue tomorrow
    vid = res["id"]; done += 1; have.add(title); os.remove(path)
    # 9 Nov owner: each song its own picture; 2-minute singles use the 2nd picture set (variants v1). Unverified channels cannot set thumbnails.
    th = next((x for x in (os.path.join(os.path.dirname(D), "long", "variants", slug, f"{code}_v1.jpg"), os.path.join(D, slug, f"thumb_{code}.jpg")) if os.path.exists(x)), None)
    if code not in VERIFIED or not th: t = "no custom thumbnail (channel not verified)" if code not in VERIFIED else "no thumbnail file"
    else:
        try: yt.thumbnails().set(videoId=vid, media_body=MediaFileUpload(th, mimetype="image/jpeg")).execute(); t = "thumb ok " + os.path.basename(th)
        except Exception as e: t = "thumb FAILED " + str(e)[-80:]
    print(f"RESULT {code} {slug} SCHEDULED {vid} public {pub} | {t}", flush=True)
print(f"RESULT {code} done today: {done}")

# ---- Shorts (owner 4 Nov): 5 per channel per day from Drive "BuBu TV Shorts/<slug>", public 08:30 11:30 14:30 17:30 20:30 IST ----
SHORT_SLOTS = [datetime.datetime(today.year, today.month, today.day, h, 30, tzinfo=ist) for h in (8, 11, 14, 17, 20)]
SHORT_SLOTS = [max(s, now + datetime.timedelta(minutes=40)) for s in SHORT_SLOTS]
sdone = 0
for slug in queue:
    if sdone >= SHORTS_PER_DAY: break
    mp = os.path.join(D, slug, f"meta_{code}.json")
    if not os.path.exists(mp): continue
    meta = json.load(open(mp, encoding="utf-8"))
    hook = str(meta.get("thumb_text", "")).strip(); song = meta["title"].split("|")[0].strip()
    title = (f"{hook} | {song} #shorts" if hook else f"{song} #shorts")[:100].strip()
    if title in have: continue
    fid = drive_file(slug, f"{slug[:3]}_{NAME[code]}_short.mp4")
    if not fid: print(f"RESULT {code} {slug} SHORT_NOT_IN_DRIVE"); continue
    path = f"{slug}_{code}_short.mp4"; fh = io.FileIO(path, "wb"); dl = MediaIoBaseDownload(fh, dr.files().get_media(fileId=fid), chunksize=32 * 2**20); ok = False
    while not ok: _, ok = dl.next_chunk()
    fh.close()
    if os.environ.get("DRY") == "1":
        print(f"RESULT {code} {slug} SHORT DRY '{title}' at {SHORT_SLOTS[sdone].astimezone(ist):%H:%M} IST", flush=True); sdone += 1; have.add(title); os.remove(path); continue
    desc = (meta["description"].split("\n\n")[0] + "\n\nFull song on our channel - BuBu TV.\n#shorts #kidssongs #rhymes")[:5000]
    sn = {"title": title, "description": desc, "tags": meta["tags"][:20] + ["shorts"], "categoryId": "27"}
    yl = code if code not in NEW else YT_LANG.get(code)
    if yl: sn.update({"defaultLanguage": yl, "defaultAudioLanguage": yl})
    pub = SHORT_SLOTS[sdone].astimezone(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    body = {"snippet": sn, "status": {"privacyStatus": "private", "publishAt": pub, "selfDeclaredMadeForKids": True, "embeddable": True, "containsSyntheticMedia": True}}
    try:
        req = yt.videos().insert(part="snippet,status", body=body, media_body=MediaFileUpload(path, chunksize=16 * 2**20, resumable=True)); res = None
        while res is None: _, res = req.next_chunk()
    except Exception as e:
        print(f"RESULT {code} {slug} SHORT STOPPED {str(e)[-200:]}"); break
    sdone += 1; have.add(title); os.remove(path)
    print(f"RESULT {code} {slug} SHORT SCHEDULED {res['id']} public {pub}", flush=True)
print(f"RESULT {code} shorts today: {sdone}")
