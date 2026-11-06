# BuBu TV long non-stop videos (owner 6 Nov 2026, Zuzu-style "zigzag"): one 30-60 min compilation per language channel per run.
#   python long_video.py <code>        env: EP (episode number: picks lead song + length + order), DRY=1 (build only, no upload)
# Songs come from Kaggle outputs / GitHub release (data/long/sources.json). Each episode starts with a different hit song, the rest in a new
# order; songs repeat when needed to reach the length. Uploaded PRIVATE (owner checks first). Re-runs never duplicate (exact title check).
import datetime, json, os, random, re, subprocess, sys, time, urllib.request
code = sys.argv[1]; EP = int(os.environ.get("EP") or 0); DRY = os.environ.get("DRY") == "1"
S = json.load(open("data/long/sources.json", encoding="utf-8")); NAME = S["name"]; L = NAME[code]
MINS = [30, 45, 60, 40][EP % 4]
def sh(c): r = subprocess.run(c, capture_output=True, text=True); return r
def dur(p):
    r = sh(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", p]); return float(r.stdout.strip() or 0)
os.makedirs("lv", exist_ok=True); os.makedirs("norm", exist_ok=True); have = {}
for slug, info in S["songs"].items():
    src = info["src"].get(code)
    if not src: continue
    raw = f"lv/{slug}.mp4"
    if "url" in src: sh(["curl", "-sSLf", "--retry", "3", "-o", raw, src["url"]])
    else:
        env = dict(os.environ, KAGGLE_API_TOKEN=os.environ.get(f"KAGGLE_KEY{src['key']}", ""), PYTHONUTF8="1"); d = f"lv/k_{slug}"
        subprocess.run(["kaggle", "kernels", "output", src["kernel"], "-p", d, "--file-pattern", "^" + re.escape(src["file"]) + "$"], env=env, capture_output=True, text=True)
        if os.path.exists(f"{d}/{src['file']}"): os.replace(f"{d}/{src['file']}", raw)
    if not os.path.exists(raw) or os.path.getsize(raw) < 1_000_000: print(f"{slug} {code} MISSING source", flush=True); continue
    n = f"norm/{slug}.mp4"   # same size/fps/codec for every song -> lossless join
    r = sh(["ffmpeg", "-y", "-loglevel", "error", "-i", raw, "-vf", "scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2,fps=24,format=yuv420p,setsar=1",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-c:a", "aac", "-ar", "48000", "-ac", "2", "-b:a", "160k", "-movflags", "+faststart", n])
    os.remove(raw)
    if r.returncode: print(slug, "encode failed", r.stderr[-200:], flush=True); continue
    have[slug] = dur(n); print(f"{slug} ok {have[slug]:.0f}s", flush=True)
leads = [s for s in S["leads"] if s in have]
if not leads or len(have) < 5: print(f"RESULT {code} NOT_ENOUGH_SONGS {len(have)}"); sys.exit(0)
lead = leads[EP % len(leads)]; rnd = random.Random(1000 * EP + len(code)); seq = [lead]; tot = have[lead]; T = MINS * 60
while tot < T:
    pool = [s for s in have if s != lead or len(seq) > len(have)]; rnd.shuffle(pool)
    for s in pool:
        if tot >= T: break
        if s in seq[-3:]: continue        # never the same song close together
        seq.append(s); tot += have[s]
    if len(seq) > 80: break
open("list.txt", "w").write("".join(f"file 'norm/{s}.mp4'\n" for s in seq))
out = f"long_{code}_ep{EP}.mp4"; r = sh(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", "list.txt", "-c", "copy", "-movflags", "+faststart", out])
if r.returncode: print(f"RESULT {code} JOIN_FAILED {r.stderr[-200:]}"); sys.exit(1)
M = round(dur(out) / 60); T0 = 0.0; chap = []
for s in seq:
    t = int(T0); chap.append(f"{t // 3600}:{t % 3600 // 60:02d}:{t % 60:02d} {S['songs'][s]['title'].get(code) or s[4:].replace('_', ' ').title()}" if t >= 3600 else f"{t // 60:02d}:{t % 60:02d} {S['songs'][s]['title'].get(code) or s[4:].replace('_', ' ').title()}"); T0 += have[s]
LN = L.capitalize(); lt = S["songs"][lead]["title"].get(code) or lead[4:]
tail = f" & More | {M} Min Non-Stop {LN} Kids Songs | BuBu TV"; title = (lt[:100 - len(tail)].strip() + tail)[:100]
meta = json.load(open(f"data/songs/{lead}/meta_{code}.json", encoding="utf-8")) if os.path.exists(f"data/songs/{lead}/meta_{code}.json") else {"description": "", "tags": []}
desc = (meta["description"].split("\n\n")[0] + f"\n\n{M} minutes of non-stop {LN} songs and rhymes for kids.\n\n" + "\n".join(chap) + "\n\n#kidssongs #nurseryrhymes #bubutv")[:5000]
print("TITLE", title); print("\n".join(chap), flush=True)
# thumbnail: lead song thumbnail + "<M> MIN NON-STOP" badge
from PIL import Image, ImageDraw, ImageFont
th = f"thumb_{code}_ep{EP}.jpg"; base = f"data/songs/{lead}/thumb_{code}.jpg"
im = Image.open(base).convert("RGB").resize((1280, 720)) if os.path.exists(base) else Image.new("RGB", (1280, 720), (255, 200, 0))
d = ImageDraw.Draw(im); f = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 64); txt = f"{M} MIN NON-STOP"
w = d.textlength(txt, font=f); d.rounded_rectangle([1280 - w - 60, 20, 1260, 110], 24, fill=(230, 30, 60)); d.text((1280 - w - 40, 28), txt, font=f, fill="white")
im.save(th, quality=90)
if DRY: print(f"RESULT {code} DRY ep{EP} {M} min {len(seq)} songs lead {lead} {os.path.getsize(out) // 1_000_000} MB"); sys.exit(0)
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
c = Credentials.from_authorized_user_info(json.loads(os.environ["YT_TOKEN"]))
if not c.valid: c.refresh(Request())
yt = build("youtube", "v3", credentials=c, cache_discovery=False)
up = yt.channels().list(part="contentDetails", mine=True).execute()["items"][0]["contentDetails"]["relatedPlaylists"]["uploads"]; have_t, tok = set(), None
while True:
    r = yt.playlistItems().list(part="snippet", playlistId=up, maxResults=50, pageToken=tok).execute(); have_t |= {i["snippet"]["title"].strip() for i in r["items"]}; tok = r.get("nextPageToken")
    if not tok or len(have_t) > 600: break
if title in have_t: print(f"RESULT {code} ALREADY_THERE {title}"); sys.exit(0)
NEW = {"ne", "ur", "sd", "mai", "hry", "ks", "mni", "bho"}; yl = code if code not in NEW else {"ne": "ne", "ur": "ur"}.get(code)
sn = {"title": title, "description": desc, "tags": (meta.get("tags") or [])[:25] + ["non stop rhymes", "kids songs"], "categoryId": "27"}
if yl: sn.update({"defaultLanguage": yl, "defaultAudioLanguage": yl})
body = {"snippet": sn, "status": {"privacyStatus": "private", "selfDeclaredMadeForKids": True, "embeddable": True, "containsSyntheticMedia": True}}
try:
    req = yt.videos().insert(part="snippet,status", body=body, media_body=MediaFileUpload(out, chunksize=32 * 2**20, resumable=True)); res = None
    while res is None: _, res = req.next_chunk()
except Exception as e: print(f"RESULT {code} STOPPED {str(e)[-200:]}"); sys.exit(0)
vid = res["id"]
try: yt.thumbnails().set(videoId=vid, media_body=MediaFileUpload(th, mimetype="image/jpeg")).execute(); t = "thumb ok"
except Exception as e: t = "thumb FAILED " + str(e)[-80:]
print(f"RESULT {code} UPLOADED_PRIVATE ep{EP} {vid} {M} min {len(seq)} songs lead {lead} {t}")
