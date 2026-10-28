"""Make ONE vertical comedy Short for one language channel and upload it publicly (owner approved 28 Oct 2026).
Picks the next not-yet-uploaded moment (ep x segment) for that channel, cuts it on exact line boundaries,
renders 1080x1920 (episode centred over a blurred copy + the episode hook as big text on top) and uploads it.
Usage: python shorts_one.py <lang>        Env: YT_TOKEN, KAGGLE_KEY<n> secrets."""
import json, os, re, subprocess, sys
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
lang = sys.argv[1]
D = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
EPS = ["ep02", "cg01", "ep04", "ep03"]          # the 4 episodes already on the channels
N_SEG = 3
ORDER = [(ep, k) for k in range(N_SEG) for ep in EPS]   # ep02#0, cg01#0, ep04#0, ep03#0, ep02#1, ...
links = json.load(open(os.path.join(D, "shorts_links.json"), encoding="utf-8"))
FUN = re.compile(r"laugh|funny|mischiev|excit|teas|playful|sarcas|shock|surpris|panic|angry|scream|giggl|proud|smug|confus|cheek|annoy|frustr|dramatic|boast", re.I)

def creds():
    c = Credentials.from_authorized_user_info(json.loads(os.environ["YT_TOKEN"]))
    if not c.valid: c.refresh(Request())
    return c
yt = build("youtube", "v3", credentials=creds(), cache_discovery=False)
# which moments are already on this channel? (marker in the description)
up = yt.channels().list(part="contentDetails", mine=True).execute()["items"][0]["contentDetails"]["relatedPlaylists"]["uploads"]
done = set()
for it in yt.playlistItems().list(part="snippet", playlistId=up, maxResults=50).execute().get("items", []):
    done.update(re.findall(r"\[s:(\w+)-(\d)\]", it["snippet"].get("description", "")))
todo = [(e, k) for e, k in ORDER if (e, str(k)) not in done and links.get(e, {}).get(lang)]
if not todo: sys.exit(0 if print("nothing left for", lang) is None else 0)
ep, seg = todo[0]
print("making", lang, ep, "moment", seg + 1, flush=True)

def timeline(ep, L):
    plan = json.load(open(os.path.join(D, "plans", f"{ep}.json")))
    lt = {x["id"]: x for x in json.load(open(os.path.join(D, "lines", f"{ep}_{L}.json"), encoding="utf-8"))}
    t, out = 0.0, []
    for s in plan["shots"]:
        ds = [lt[x]["duration_s"] for x in s["lines"] if x in lt]; lead = s.get("lead", 0.12)
        Ln = max(1.2, lead + sum(ds) + 0.18 * max(0, len(ds) - 1) + 0.22) if ds else (s["hi_dur"] if s.get("fixed") else min(s["hi_dur"], 2.2))
        Ln = round(Ln * 24) / 24
        out.append({"id": s["id"], "start": t, "end": t + Ln, "lines": [lt[x] for x in s["lines"] if x in lt]}); t += Ln
    return out
# choose moments on the Hindi timeline (same shots in every language), then use this language's timing
hi = timeline(ep, "hi")
cands = []
for i in range(len(hi)):
    j, best = i, None
    while j < len(hi) and hi[j]["end"] - hi[i]["start"] <= 55:
        dur = hi[j]["end"] - hi[i]["start"]
        if dur >= 30:
            lines = [l for s in hi[i:j + 1] for l in s["lines"]]
            score = sum(bool(FUN.search(l.get("emotion", ""))) for l in lines) + 0.3 * len(lines)
            if not best or score > best[0]: best = (score, i, j)
        j += 1
    if best: cands.append(best)
cands.sort(reverse=True); picks = []
for sc, i, j in cands:
    if all(j < a or i > b for _, a, b in picks): picks.append((sc, i, j))
    if len(picks) == N_SEG: break
picks.sort(key=lambda p: p[1])
_, i, j = picks[seg]
me = timeline(ep, lang)
ids = [s["id"] for s in hi[i:j + 1]]
shots = [s for s in me if s["id"] in ids]
start, end = shots[0]["start"], shots[-1]["end"]
while end - start > 58 and len(shots) > 1: shots.pop(); end = shots[-1]["end"]
print(f"moment shots {ids[0]}..{ids[-1]}  {start:.1f}-{end:.1f}s ({end - start:.1f}s)", flush=True)
# download the finished episode from Kaggle
src = json.load(open(os.path.join(D, "sources.json")))[ep]
env = dict(os.environ, KAGGLE_API_TOKEN=os.environ[f"KAGGLE_KEY{src['key']}"], PYTHONUTF8="1")
os.makedirs("dl", exist_ok=True); name = f"{ep}_{lang}.mp4"
subprocess.run(["kaggle", "kernels", "output", src["kernel"], "-p", "dl", "--file-pattern", "^" + re.escape(name) + "$"], env=env, capture_output=True, text=True)
video = os.path.join("dl", name)
if not os.path.exists(video): sys.exit("download failed")
# hook text overlay (proper Indic shaping through Pillow + raqm)
meta = json.load(open(os.path.join(D, "meta", f"{ep}_{lang}.json"), encoding="utf-8"))
hook = re.split(r"\s*[|｜]\s*", meta["title"])[0]
hook_txt = re.sub(r"[\U0001F000-\U0001FAFF☀-➿️]", "", hook).strip()
from PIL import Image, ImageDraw, ImageFont, features
FONTS = {"te": "NotoSansTelugu", "hi": "NotoSansDevanagari", "mr": "NotoSansDevanagari", "ta": "NotoSansTamil", "kn": "NotoSansKannada",
         "ml": "NotoSansMalayalam", "bn": "NotoSansBengali", "as": "NotoSansBengali", "gu": "NotoSansGujarati", "pa": "NotoSansGurmukhi",
         "or": "NotoSansOriya", "en": "NotoSans"}
fp = next((p for p in [f"/usr/share/fonts/truetype/noto/{FONTS[lang]}-Bold.ttf", f"/usr/share/fonts/truetype/noto/{FONTS[lang]}-Regular.ttf"] if os.path.exists(p)), None)
ov = Image.new("RGBA", (1080, 1920), (0, 0, 0, 0)); dr = ImageDraw.Draw(ov)
if fp and (features.check("raqm") or lang == "en"):
    eng = ImageFont.Layout.RAQM if features.check("raqm") else ImageFont.Layout.BASIC
    size = 96
    while size > 48:
        f = ImageFont.truetype(fp, size, layout_engine=eng); words = hook_txt.split(); lines, cur = [], ""
        for w in words:
            tst = (cur + " " + w).strip()
            if dr.textlength(tst, font=f) <= 980: cur = tst
            else: lines.append(cur); cur = w
        lines.append(cur)
        if len(lines) <= 3: break
        size -= 8
    y = 520 - len(lines) * (size + 18)
    for ln in lines:
        w = dr.textlength(ln, font=f)
        dr.text(((1080 - w) / 2, y), ln, font=f, fill=(255, 230, 0, 255), stroke_width=8, stroke_fill=(0, 0, 0, 255)); y += size + 18
else:
    print("no Indic text shaping available - Short made without the top text", flush=True)
ov.save("overlay.png")
subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{start:.3f}", "-t", f"{end - start:.3f}", "-i", video, "-i", "overlay.png", "-filter_complex",
                "[0:v]split[a][b];[a]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,boxblur=24:2,eq=brightness=-0.10[bg];"
                "[b]scale=1080:-2[fg];[bg][fg]overlay=(W-w)/2:(H-h)/2[v1];[v1][1:v]overlay=0:0,fps=30[v]",
                "-map", "[v]", "-map", "0:a", "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-c:a", "aac", "-b:a", "160k", "short.mp4"], check=True)
if os.environ.get("DRY_RUN"):
    print("DRY RUN - not uploaded", lang, ep, seg + 1, f"{end - start:.1f}s", flush=True); sys.exit(0)
long_id = links[ep][lang]
title = (hook + " #shorts")[:100]
desc = f"{hook}\n\nFull episode / పూర్తి ఎపిసోడ్ ▶ https://youtu.be/{long_id}\n\n#shorts #cartoon #comedy\n[s:{ep}-{seg}]"
if lang != "te": desc = desc.replace(" / పూర్తి ఎపిసోడ్", "")
body = {"snippet": {"title": title, "description": desc, "tags": (meta.get("tags") or [])[:10] + ["shorts"], "categoryId": "24",
                    "defaultLanguage": lang, "defaultAudioLanguage": lang},
        "status": {"privacyStatus": "public", "selfDeclaredMadeForKids": False}}
req = yt.videos().insert(part="snippet,status", body=body, media_body=MediaFileUpload("short.mp4", mimetype="video/mp4", resumable=True))
resp = None
while resp is None: _, resp = req.next_chunk()
print("UPLOADED", lang, ep, seg + 1, "https://youtube.com/shorts/" + resp["id"], flush=True)
