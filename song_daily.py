# BuBu TV daily song timer (owner 3 Nov 2026): Google Drive -> YouTube, 5 new songs per channel per day, going public at 07:00 10:00 13:00 16:00 19:00 IST.
#   python song_daily.py <code>      (one language channel; GitHub matrix runs all 20)
# Queue = data/songs/queue.json (only songs Claude checked). A song counts as done on a channel when a video with its exact title exists there,
# so re-runs never duplicate. Quota/upload errors stop this channel for today; the next day continues where it stopped.
import datetime, io, json, os, sys, time
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload, MediaIoBaseDownload
code = sys.argv[1]
# 10 Nov owner: 2-minute songs again. 8 verified channels (long videos + own thumbnails): 2 a day. 12 others (no long videos): 4 a day. No Shorts. 100 uploads/day shared.
VERIFIED = {"hi", "te", "ta", "kn", "mr", "bn", "en", "ur"}
# 11 Nov owner: "1 to 2 videos without repetitive content" -> 2 new songs a day on every channel
# 11 Nov owner (later): "one song everyday and remaining 2 to 3 or 4 should be shorts in all languages" -> 1 song + 3 Shorts per channel
PER_DAY = int(os.environ.get("SONGS_PER_DAY") or 1); SLOTS_IST = [18] if code in VERIFIED else [19]
if os.environ.get("SLOTS"): SLOTS_IST = [int(h) for h in os.environ["SLOTS"].split(",")]   # hand runs: own hours (e.g. extra songs later the same day)
PER_DAY = min(PER_DAY, len(SLOTS_IST))
# 10 Nov owner: long videos stopped; "I'm talking about 2 min songs" -> the 8 verified channels get 3 more 2-minute songs in their place (5 a day). No Shorts.
SHORTS_PER_DAY = int(os.environ.get("SHORTS_PER_DAY") or 3)   # 11 Nov owner: 3 Shorts a day, made here from the full song (2 different parts per song)
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
# 11 Nov: titles were changed later, so a song is ALSO recognised by its NAME (the part before the first '|') on any 1-4 minute video -> never upload the same song twice
import re as _re
def _secs(d):
    m = _re.match(r"P(?:\d+D)?T?(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", d or "")
    return sum(int(x or 0) * k for x, k in zip(m.groups(), (3600, 60, 1))) if m else 0
on_names, ids, tok = set(), [], None
def _core(t): return _re.sub(r"[^\w]+", " ", t.split("|")[0].split("&")[0].split("#")[0]).strip().lower()
while True:
    r = retry(lambda: yt.playlistItems().list(part="contentDetails", playlistId=up, maxResults=50, pageToken=tok).execute())
    ids += [i["contentDetails"]["videoId"] for i in r["items"]]; tok = r.get("nextPageToken")
    if not tok: break
for k in range(0, len(ids), 50):
    for v in retry(lambda: yt.videos().list(part="snippet,contentDetails", id=",".join(ids[k:k + 50])).execute())["items"]:
        if 61 <= _secs(v["contentDetails"].get("duration")) <= 240: on_names.add(_core(v["snippet"]["title"]))
print(f"RESULT {code} channel has {len(ids)} videos, {len(on_names)} song names", flush=True)
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
        if _core(title) in on_names:
            print(f"RESULT {code} {slug} SKIP already on channel (same song name, other title)", flush=True); continue
    if fid:
        fh = io.FileIO(path, "wb"); dl = MediaIoBaseDownload(fh, dr.files().get_media(fileId=fid), chunksize=64 * 2**20); ok = False
        while not ok: _, ok = dl.next_chunk()
        fh.close()
    else:   # 4 Nov: owner's Drive is full (15 GB) -> fall back to the song's Kaggle output (release.json says which kernel/key)
        import subprocess, re as _re
        rp = os.path.join(D, slug, "release.json")   # 11 Nov: a song missing in Drive with no Kaggle record is SKIPPED (it crashed the whole Tamil run before)
        if not os.path.exists(rp): print(f"RESULT {code} {slug} NOT_IN_DRIVE - skipped, next song", flush=True); continue
        src = json.load(open(rp, encoding="utf-8"))["files"].get(code)
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

# ---- Shorts (11 Nov owner): 3 per channel per day, cut HERE from the full 2-minute song in Drive (no ready-made file needed).
# Each song gives 2 different Shorts (Part 1 = first half, Part 2 = second half). A Short is never repeated (its exact title is checked).
import subprocess
SHORT_SLOTS = [datetime.datetime(today.year, today.month, today.day, h, m, tzinfo=ist) for h, m in ((9, 30), (13, 30), (21, 0))]
SHORT_SLOTS = [max(s, now + datetime.timedelta(minutes=40)) for s in SHORT_SLOTS]
sdone = 0
def _on(sl):      # Shorts first for songs whose full video is already on this channel (so 'Full song on our channel' is true)
    mp = os.path.join(D, sl, f"meta_{code}.json")
    if not os.path.exists(mp): return 2
    t = json.load(open(mp, encoding="utf-8"))["title"][:100].strip(); return 0 if (t in have or _core(t) in on_names) else 1
squeue = sorted(queue, key=_on)
for part in (1, 2):
    for slug in squeue:
        if sdone >= SHORTS_PER_DAY: break
        mp = os.path.join(D, slug, f"meta_{code}.json")
        if not os.path.exists(mp): continue
        meta = json.load(open(mp, encoding="utf-8")); song = meta["title"].split("|")[0].strip(); hook = str(meta.get("thumb_text", "")).strip()
        title = ((f"{hook} | {song} #shorts" if hook else f"{song} #shorts") if part == 1 else f"{song} | Part 2 #shorts")[:100].strip()
        if title in have: continue
        fid = drive_file(slug, f"{slug[:3]}_{NAME[code]}.mp4")
        if not fid: continue
        full = f"{slug}_{code}_full.mp4"; fh = io.FileIO(full, "wb"); dl = MediaIoBaseDownload(fh, dr.files().get_media(fileId=fid), chunksize=32 * 2**20); ok = False
        while not ok: _, ok = dl.next_chunk()
        fh.close()
        try: dur = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", full], capture_output=True, text=True).stdout.strip())
        except Exception: dur = 120.0
        L = min(42.0, max(20.0, dur / 2 - 4)); st = 6.0 if part == 1 else max(6.0, dur / 2)
        if st + L > dur - 1: L = max(15.0, dur - 1 - st)
        path = f"{slug}_{code}_p{part}_short.mp4"
        # 11 Nov owner: "full screen even in vertical shorts ... zoom in to the video" -> fill 1080x1920 by zooming into the centre (no blurred bars)
        # + "our transparent name and logo too": logo top-right + see-through "BUBU TV" travelling slowly, same as the songs and long videos
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
        if r.returncode or not os.path.exists(path): print(f"RESULT {code} {slug} SHORT CUT FAILED {r.stderr[-200:]}"); continue
        if os.environ.get("DRY") == "1":
            print(f"RESULT {code} {slug} SHORT DRY '{title}' {st:.0f}-{st + L:.0f}s at {SHORT_SLOTS[sdone].astimezone(ist):%H:%M} IST", flush=True); sdone += 1; have.add(title); os.remove(path); continue
        desc = (meta["description"].split("\n\n")[0] + "\n\nFull song on our channel - BuBu TV.\n#shorts #kidssongs #rhymes")[:5000]
        sn = {"title": title, "description": desc, "tags": meta["tags"][:20] + ["shorts"], "categoryId": "27"}
        if code in YT_LANG: sn.update(defaultLanguage=YT_LANG[code], defaultAudioLanguage=YT_LANG[code])
        pub = SHORT_SLOTS[sdone].astimezone(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        body = {"snippet": sn, "status": {"privacyStatus": "private", "publishAt": pub, "selfDeclaredMadeForKids": True, "embeddable": True, "containsSyntheticMedia": True}}
        try:
            req = yt.videos().insert(part="snippet,status", body=body, media_body=MediaFileUpload(path, chunksize=16 * 2**20, resumable=True)); res = None
            while res is None: _, res = req.next_chunk()
        except Exception as e:
            print(f"RESULT {code} {slug} SHORT STOPPED {str(e)[-200:]}"); os.remove(path); break
        os.remove(path); sdone += 1; have.add(title)
        print(f"RESULT {code} {slug} SHORT SCHEDULED {res['id']} public {pub}", flush=True)
print(f"RESULT {code} shorts today: {sdone}")
