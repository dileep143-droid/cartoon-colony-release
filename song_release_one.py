# BuBu TV kids-song release on GitHub Actions (3 Nov 2026; owner rule: Kaggle -> GitHub -> YouTube, never download to the laptop).
#   python song_release_one.py <slug> <code> <privacy>
#   1) download S0x_<language>.mp4 from the song's Kaggle kernel output  2) skip if the channel already has a video with this exact title (no duplicates on re-runs)
#   3) upload: made for kids, Education (27), containsSyntheticMedia=True (AI music is the main focus -> honest "Yes"), title/description/tags from data/songs/<slug>/meta_<code>.json
#   4) custom thumbnail data/songs/<slug>/thumb_<code>.jpg (fails on channels without phone verification - not an error)
import json, os, re, subprocess, sys
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
slug, code, privacy = sys.argv[1:4]
D = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "songs", slug)
cfg = json.load(open(os.path.join(D, "release.json"), encoding="utf-8")); meta = json.load(open(os.path.join(D, f"meta_{code}.json"), encoding="utf-8"))
NEW = {"ne", "ur", "sd", "mai", "hry", "ks", "mni", "bho"}; YT_LANG = {"ne": "ne", "ur": "ur"}
src = cfg["files"][code]                      # {"kernel": ..., "key": n, "file": "S04_hindi.mp4"}
env = dict(os.environ, KAGGLE_API_TOKEN=os.environ[f"KAGGLE_KEY{src['key']}"], PYTHONUTF8="1"); os.makedirs("dl", exist_ok=True)
r = subprocess.run(["kaggle", "kernels", "output", src["kernel"], "-p", "dl", "--file-pattern", "^" + re.escape(src["file"]) + "$"], env=env, capture_output=True, text=True)
video = os.path.join("dl", src["file"])
if not os.path.exists(video): sys.exit("download failed: " + (r.stdout + r.stderr)[-400:])
print("downloaded", os.path.getsize(video) // 1_000_000, "MB", flush=True)
c = Credentials.from_authorized_user_info(json.loads(os.environ["YT_TOKEN"]))
if not c.valid: c.refresh(Request())
yt = build("youtube", "v3", credentials=c, cache_discovery=False)
title = meta["title"][:100]
up = yt.channels().list(part="contentDetails", mine=True).execute()["items"][0]["contentDetails"]["relatedPlaylists"]["uploads"]
for it in yt.playlistItems().list(part="snippet", playlistId=up, maxResults=50).execute()["items"]:
    if it["snippet"]["title"].strip() == title.strip():
        print(f"RESULT {slug} {code} ALREADY {it['snippet']['resourceId']['videoId']}"); sys.exit(0)
sn = {"title": title, "description": meta["description"][:5000], "tags": meta["tags"][:30], "categoryId": "27"}
yl = code if code not in NEW else YT_LANG.get(code)
if yl: sn.update({"defaultLanguage": yl, "defaultAudioLanguage": yl})
body = {"snippet": sn, "status": {"privacyStatus": privacy, "selfDeclaredMadeForKids": True, "embeddable": True, "containsSyntheticMedia": True}}
req = yt.videos().insert(part="snippet,status", body=body, media_body=MediaFileUpload(video, chunksize=16 * 2**20, resumable=True))
res = None
while res is None: _, res = req.next_chunk()
vid = res["id"]; print(f"RESULT {slug} {code} UPLOADED {vid}", flush=True)
th = os.path.join(D, f"thumb_{code}.jpg")
try: yt.thumbnails().set(videoId=vid, media_body=MediaFileUpload(th, mimetype="image/jpeg")).execute(); print("thumb ok")
except Exception as e: print("thumb FAILED (channel not phone verified?)", str(e)[-150:])
