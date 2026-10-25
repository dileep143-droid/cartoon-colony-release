# Runs on GitHub Actions (owner approved 25 Oct 2026): one episode x one language ->
#   1) download the finished 1440p video straight from its Kaggle kernel output (no laptop, no R2)
#   2) add our drum-free music bed (sneaky / sad / warm loops; -18 dB in gaps, -28 dB under speech)
#   3) upload to that language's channel (NOT made for kids, Entertainment), custom thumbnail, search packaging + English localization
#   4) copy the final file to the owner's Google Drive (folder "Cartoon Colony Episodes/<lang>")
#   python release_one.py <ep> <lang> <privacy> [publishAt ISO, e.g. 2026-10-26T12:30:00Z]
import json, os, re, subprocess, sys, wave
import numpy as np
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
ep, lang, privacy = sys.argv[1:4]; publish_at = sys.argv[4] if len(sys.argv) > 4 and sys.argv[4] else None
D = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data"); SR = 48000
src = json.load(open(os.path.join(D, "sources.json")))[ep]
# 1) Kaggle -> runner
env = dict(os.environ, KAGGLE_API_TOKEN=os.environ[f"KAGGLE_KEY{src['key']}"], PYTHONUTF8="1")
os.makedirs("dl", exist_ok=True); name = f"{ep}_{lang}.mp4"
r = subprocess.run(["kaggle", "kernels", "output", src["kernel"], "-p", "dl", "--file-pattern", "^" + re.escape(name) + "$"], env=env, capture_output=True, text=True)
video = os.path.join("dl", name)
if not os.path.exists(video): sys.exit("download failed: " + (r.stdout + r.stderr)[-400:])
print("downloaded", os.path.getsize(video) // 1_000_000, "MB", flush=True)
# 2) music bed on the exact timeline of the assembly (same maths as asm_kernel_tpl.py / add_music.py)
plan = json.load(open(os.path.join(D, "plans", f"{ep}.json")))
lt = {x["id"]: x for x in json.load(open(os.path.join(D, "lines", f"{ep}_{lang}.json"), encoding="utf-8"))}
pcm = lambda p: np.frombuffer(subprocess.run(["ffmpeg", "-v", "error", "-i", p, "-ac", "1", "-ar", str(SR), "-f", "s16le", "-"], capture_output=True).stdout, np.int16).astype(np.float32)
loops = {k: pcm(os.path.join(D, "music", f"{k}.mp3")) for k in ("sneaky", "sad", "warm")}
for k in loops: loops[k] /= (np.sqrt((loops[k] ** 2).mean()) or 1)
SAD = re.compile(r"sad|worr|scar|afraid|cry|guilt|hurt|ashamed|tearful|emotional|regret|fear|lonely|nervous|panic", re.I)
t, speech, scene_t, scene_emo = 0.0, [], {}, {}
for s in plan["shots"]:
    ds = [lt[x]["duration_s"] for x in s["lines"] if x in lt]; lead = s.get("lead", 0.12)
    L = max(1.2, lead + sum(ds) + 0.18 * max(0, len(ds) - 1) + 0.22) if ds else (s["hi_dur"] if s.get("fixed") else min(s["hi_dur"], 2.2)); L = round(L * 24) / 24
    c = lead
    for x in s["lines"]:
        if x in lt:
            speech.append((t + c, t + c + lt[x]["duration_s"])); scene_emo.setdefault(s["scene"], []).append(lt[x].get("emotion", "")); c += lt[x]["duration_s"] + 0.18
    a, b = scene_t.get(s["scene"], (t, t)); scene_t[s["scene"]] = (min(a, t), t + L); t += L
audio = pcm(video); n = len(audio); sp = np.zeros(n, bool)
for a, b in speech: sp[int(a * SR):int(b * SR)] = True
dlg = np.sqrt((audio[sp] ** 2).mean()) if sp.any() else np.sqrt((audio ** 2).mean())
bed = np.zeros(n, np.float32); order = sorted(scene_t, key=lambda k: scene_t[k][0])
for k in order:
    a, b = scene_t[k]; emo = scene_emo.get(k, [])
    mood = "warm" if k == order[-1] else ("sad" if emo and sum(bool(SAD.search(m)) for m in emo) / len(emo) > 0.4 else "sneaky")
    i0, i1 = int(a * SR), min(n, int(b * SR) + int(1.5 * SR)); lp = loops[mood]; seg = np.tile(lp, (i1 - i0) // len(lp) + 2)[:i1 - i0].copy()
    f = min(len(seg), int(1.5 * SR)); seg[:f] *= np.linspace(0, 1, f); seg[-f:] *= np.linspace(1, 0, f); bed[i0:i1] += seg
g = np.where(sp, 10 ** (-28 / 20), 10 ** (-18 / 20)).astype(np.float32); w = int(0.25 * SR); g = np.convolve(g, np.ones(w, np.float32) / w, "same")
out = np.clip(audio + bed * g * dlg, -32767, 32767).astype(np.int16)
with wave.open("mix.wav", "wb") as wv: wv.setnchannels(1); wv.setsampwidth(2); wv.setframerate(SR); wv.writeframes(out.tobytes())
final = f"{ep}_{lang}.mp4"; os.replace(video, "in.mp4")
subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", "in.mp4", "-i", "mix.wav", "-map", "0:v", "-map", "1:a", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-shortest", final], check=True)
os.remove("in.mp4"); print("music added", flush=True)


def creds(js):
    c = Credentials.from_authorized_user_info(json.loads(js))
    if not c.valid: c.refresh(Request())
    return c


# 3) YouTube
m = json.load(open(os.path.join(D, "meta", f"{ep}_{lang}.json"), encoding="utf-8"))
yt = build("youtube", "v3", credentials=creds(os.environ["YT_TOKEN"]), cache_discovery=False)
status = {"privacyStatus": "private" if publish_at else privacy, "selfDeclaredMadeForKids": False, "embeddable": True}
if publish_at: status["publishAt"] = publish_at
body = {"snippet": {"title": m["title"][:100], "description": m["description"][:4900], "tags": m["tags"], "categoryId": "24", "defaultLanguage": lang,
                    "defaultAudioLanguage": lang}, "status": status}
if m.get("localizations"): body["localizations"] = m["localizations"]
req = yt.videos().insert(part="snippet,status" + (",localizations" if m.get("localizations") else ""), body=body,
                         media_body=MediaFileUpload(final, chunksize=32 * 1024 * 1024, resumable=True, mimetype="video/mp4"))
resp = None
while resp is None: st, resp = req.next_chunk()
vid = resp["id"]; print("uploaded https://youtu.be/" + vid, flush=True)
try: yt.thumbnails().set(videoId=vid, media_body=MediaFileUpload(os.path.join(D, "thumbs", lang, f"{ep}.jpg"), mimetype="image/jpeg")).execute(); print("thumbnail set")
except Exception as ex: print("thumbnail NOT set:", str(ex)[-160:])
rb = yt.videos().list(part="snippet,status", id=vid).execute()["items"][0]
res = {"ep": ep, "lang": lang, "video_id": vid, "privacy": rb["status"]["privacyStatus"], "publishAt": rb["status"].get("publishAt"),
       "madeForKids": rb["status"].get("madeForKids"), "category": rb["snippet"]["categoryId"], "tags": len(rb["snippet"].get("tags", []))}
# 4) Google Drive copy (drive.file scope: only files this app creates)
if os.environ.get("DRIVE_TOKEN"):
    try:
        dr = build("drive", "v3", credentials=creds(os.environ["DRIVE_TOKEN"]), cache_discovery=False)
        def folder(nm, parent=None):
            q = f"name='{nm}' and mimeType='application/vnd.google-apps.folder' and trashed=false" + (f" and '{parent}' in parents" if parent else "")
            f = dr.files().list(q=q, fields="files(id)").execute().get("files", [])
            return f[0]["id"] if f else dr.files().create(body={"name": nm, "mimeType": "application/vnd.google-apps.folder", **({"parents": [parent]} if parent else {})}, fields="id").execute()["id"]
        pid = folder(lang, folder("Cartoon Colony Episodes"))
        up = dr.files().create(body={"name": final, "parents": [pid]}, media_body=MediaFileUpload(final, chunksize=64 * 1024 * 1024, resumable=True, mimetype="video/mp4"), fields="id")
        resp = None
        while resp is None: st, resp = up.next_chunk()
        res["drive_file"] = resp["id"]; print("saved to Google Drive", flush=True)
    except Exception as ex: res["drive_error"] = str(ex)[-200:]; print("Drive copy FAILED (YouTube upload is fine):", str(ex)[-200:], flush=True)
json.dump(res, open(f"result_{ep}_{lang}.json", "w"), ensure_ascii=False); print(json.dumps(res))
