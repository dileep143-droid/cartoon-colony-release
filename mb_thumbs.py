# Mahabharatam episode thumbnails on GitHub (27 Nov 2026), same template as E:/mb_builds/thumbs/make_thumbs.py (MB 02 style).
#   python mb_thumbs.py cand   -> one frame per candidate story clip (data/mb/cand.json) + 4x4 contact sheets (artifact) ; frames kept in R2 tmp
#   python mb_thumbs.py make   -> renders data/mb/thumbs.json with headless Chrome -> R2 s2work/mbup/thumbs/<name>.jpg (+ artifact)
import json, os, subprocess, sys, time, tempfile
import boto3
from botocore.config import Config
from PIL import Image, ImageDraw
B = "eduorbex-media"; TMP = "s2work/tmp_mbup1127/"
S3 = boto3.client("s3", endpoint_url=os.environ["CF_R2_ENDPOINT"], aws_access_key_id=os.environ["CF_R2_ACCESS_KEY_ID"],
                  aws_secret_access_key=os.environ["CF_R2_SECRET_ACCESS_KEY"], region_name="auto", config=Config(signature_version="s3v4"))
D = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "mb")
os.makedirs("out", exist_ok=True)
mode = sys.argv[1]
if mode == "cand":
    C = json.load(open(os.path.join(D, "cand.json")))
    for ep, clips in C.items():
        keys = [o["Key"] for o in S3.list_objects_v2(Bucket=B, Prefix=f"s2work/{ep}/assets/", MaxKeys=1000).get("Contents", [])]
        S = Image.new("RGB", (4 * 480, 4 * 270)); dr = ImageDraw.Draw(S)
        for i, c in enumerate(clips[:16]):
            k = sorted(x for x in keys if os.path.basename(x).startswith(c + "_") and x.endswith(".mp4"))
            if not k: print("no clip", ep, c); continue
            url = S3.generate_presigned_url("get_object", Params={"Bucket": B, "Key": k[0]}, ExpiresIn=3600)
            p = f"out/{ep}_{c}.jpg"
            subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-ss", "2.5", "-i", url, "-frames:v", "1", "-vf", "scale=1280:-2", "-q:v", "2", p])
            if not os.path.exists(p): print("frame failed", ep, c); continue
            S3.upload_file(p, B, TMP + "cand/" + os.path.basename(p))
            S.paste(Image.open(p).resize((480, 270)), ((i % 4) * 480, (i // 4) * 270)); dr.rectangle(((i % 4) * 480, (i // 4) * 270, (i % 4) * 480 + 70, (i // 4) * 270 + 22), fill="black")
            dr.text(((i % 4) * 480 + 6, (i // 4) * 270 + 5), c, fill="yellow")
        S.save(f"out/sheet_{ep}.jpg", quality=80); print("sheet", ep)
        for f in os.listdir("out"):
            if f.startswith(ep + "_"): os.remove("out/" + f)
    sys.exit(0)

# ---- make ----
A = "assets"; os.makedirs(A, exist_ok=True)
for f in ("me_big.png", "dk_logo_circle.png", "tpl.css"): S3.download_file(B, TMP + "assets/" + f, os.path.join(A, f))
CSS = open(os.path.join(A, "tpl.css"), encoding="utf-8").read()
CSS = CSS.replace('"Nirmala UI","Noto Sans Telugu",sans-serif', '"Noto Sans Telugu","Noto Sans Devanagari","Noto Sans Tamil","Noto Sans",sans-serif')
CSS = CSS.replace('"Arial Black",Arial,sans-serif', '"DejaVu Sans",sans-serif')
FIT = ("<script>for(const c of ['t1','t2']){const e=document.querySelector('.'+c);let s=parseFloat(getComputedStyle(e).fontSize);"
       "while(e.getBoundingClientRect().right>1250&&s>30){s-=2;e.style.fontSize=s+'px';}}</script>")
def shot(html, png):
    prof = tempfile.mkdtemp(prefix="chr_")
    subprocess.run(["google-chrome", "--headless=new", "--no-sandbox", "--disable-gpu", f"--user-data-dir={prof}", "--hide-scrollbars", "--force-device-scale-factor=1",
                    "--virtual-time-budget=8000", "--window-size=1280,720", f"--screenshot={png}", "file://" + os.path.abspath(html)], timeout=120,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return os.path.exists(png) and os.path.getsize(png) > 0
T = json.load(open(os.path.join(D, "thumbs.json"), encoding="utf-8"))
only = [x for x in (os.environ.get("ONLY") or "").split(",") if x]
for t in T:
    if only and t["name"] not in only: continue
    bgf = os.path.join(A, os.path.basename(t["bg"])); S3.download_file(B, t["bg"], bgf)
    html = (f'<!doctype html><html><head><meta charset="utf-8"><style>{CSS}.bg{{background:url({os.path.basename(bgf)}) {t["pos"]} no-repeat;{"transform:scaleX(-1);" if t.get("flip") else ""}}}</style></head><body>'
            f'<div class="bg"></div><div class="shade"></div><img class="me" src="me_big.png"><div class="badge">{t["badge"]}</div><img class="logo" src="dk_logo_circle.png">'
            f'<div class="t t1">{t["l1"]}</div><div class="t t2">{t["l2"]}</div>{FIT}</body></html>')
    hp = os.path.join(A, t["name"] + ".html"); open(hp, "w", encoding="utf-8").write(html)
    png = os.path.join(A, t["name"] + ".png")
    if not shot(hp, png): print("RESULT render FAILED", t["name"]); continue
    jp = f"out/{t['name']}.jpg"; Image.open(png).convert("RGB").save(jp, quality=92)
    S3.upload_file(jp, B, f"s2work/mbup/thumbs/{t['name']}.jpg"); print("RESULT thumb OK", t["name"], os.path.getsize(jp) // 1000, "KB")
