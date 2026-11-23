# Dileep Explains: render ONE Short on a GitHub runner (CPU only), same edit as the Kaggle kernel shorts_kernel2.py (23 Nov 2026 test).
#   python shorts_render.py <name> <mode>     mode = full     : alignment + LatentSync 1.5 lip-sync on CPU + assembly
#                                             mode = assemble : face circles + timing already made elsewhere (Kaggle GPU) -> assembly only
# Inputs: job JSON from R2 (<prefix>/jobs/<name>.json, made on the laptop by gh_job.py) with R2 KEYS only. Everything is read and
# written with boto3 + the repo secrets: no link, no media, no script text ever goes into the repo, an artifact or the public log.
# Output: <job.out>/sh_<name>.mp4 (+ _720.mp4, timing.json, stages.json, face/ clips + align.json, cmp/ side-by-side vs job.ref).
import os, sys, json, subprocess, time, tarfile, math, random, re, threading, glob
NAME, MODE = sys.argv[1], (sys.argv[2] if len(sys.argv) > 2 else "full")
PREFIX = os.environ.get("JOB_PREFIX", "gh_test"); assert PREFIX.startswith("gh_")
BUCKET = "eduorbex-media"
import boto3
from botocore.config import Config
S3 = boto3.client("s3", endpoint_url=os.environ["CF_R2_ENDPOINT"], aws_access_key_id=os.environ["CF_R2_ACCESS_KEY_ID"],
                  aws_secret_access_key=os.environ["CF_R2_SECRET_ACCESS_KEY"], region_name="auto", config=Config(signature_version="s3v4"))
JOB = json.loads(S3.get_object(Bucket=BUCKET, Key=f"s2work/shorts1/{PREFIX}/jobs/{NAME}.json")["Body"].read())
OUT = JOB["out"]; assert OUT.startswith(f"s2work/shorts1/{PREFIX}/"), "test runs never write outside the test prefix"
ROOT = "/tmp/sr"; IN = f"{ROOT}/in"; T = f"{ROOT}/w"; W = f"{ROOT}/out"; LS = f"{ROOT}/ls"
for d in (IN, T, W): os.makedirs(d, exist_ok=True)
T0 = time.time(); random.seed(7)
STAGES = {}; _st = {}
def put(path, key, ctype="application/octet-stream"): S3.upload_file(path, BUCKET, OUT + key, ExtraArgs={"ContentType": ctype})
def put_json(obj, key): S3.put_object(Bucket=BUCKET, Key=OUT + key, Body=json.dumps(obj, ensure_ascii=False).encode(), ContentType="application/json")
def stage(n):   # start stage n (ends the previous one); minutes go to the log and to R2 at once (live progress)
    now = time.time()
    for k in list(_st):
        STAGES[k] = round((now - _st.pop(k)) / 60, 2); print(f"STAGE {k}: {STAGES[k]} min", flush=True)
    if n: _st[n] = now
    STAGES["_total"] = round((now - T0) / 60, 2); STAGES["_now"] = n
    try: put_json(STAGES, "stages.json")
    except Exception as e: print("stages upload failed", type(e).__name__, flush=True)
def sh(c, quiet=False):   # commands hold local paths only (no links): safe for a public log
    r = subprocess.run(c, shell=True, capture_output=True, text=True)
    if not quiet or r.returncode: print(f"+ [{time.time() - T0:.0f}s]", c[:160], "-> rc", r.returncode, flush=True)
    if r.returncode: print(r.stdout[-600:], r.stderr[-1500:], flush=True)
    return r.returncode
def dur(p): return float(subprocess.run(f"ffprobe -v error -show_entries format=duration -of csv=p=0 {p}", shell=True, capture_output=True, text=True).stdout.strip() or 0)
sh("nproc; free -g | head -2; df -h / /tmp | tail -2")

stage("download")
for n, k in JOB["files"].items():
    for t in range(4):
        try: S3.download_file(BUCKET, k, f"{IN}/{n}"); break
        except Exception as e: print("retry", n, type(e).__name__, flush=True); time.sleep(5 * (t + 1))
    else: raise RuntimeError("download failed " + n)
tarfile.open(f"{IN}/caps.tar").extractall(f"{IN}/caps")
TAIL = 0.2
sh(f"ffmpeg -y -loglevel error -i {IN}/voice.flac -af apad=pad_dur={TAIL} -ar 48000 -ac 2 {T}/voice.wav"); D = dur(f"{T}/voice.wav"); print("voice+tail", D, flush=True)
sh(f"ffmpeg -y -loglevel error -i {T}/voice.wav -ar 16000 -ac 1 {T}/v16.wav")

if MODE == "full":
    # ---------- 1) word timing by MMS forced alignment (same code as the kernel, on CPU) ----------
    stage("align")
    import soundfile as sf, torch, uroman as ur
    from transformers import Wav2Vec2ForCTC, AutoTokenizer
    dev = "cpu"; torch.set_num_threads(os.cpu_count() or 4)
    U = ur.Uroman(); R = "MahmoudAshraf/mms-300m-1130-forced-aligner"
    model = Wav2Vec2ForCTC.from_pretrained(R).to(dev).eval(); tk = AutoTokenizer.from_pretrained(R); V = tk.get_vocab(); blank = V.get("<blank>", tk.pad_token_id)
    def norm(w): return "".join(c for c in w.lower() if (c in V and c.isalpha()) or (c == "'" and c in V))
    x = torch.from_numpy(sf.read(f"{T}/v16.wav", dtype="float32")[0]); SR = 16000; HOP = 320; WIN = 20 * SR; CTX = 2 * SR; ems = []; xn = (x - x.mean()) / (x.std() + 1e-7)
    for s in range(0, x.numel(), WIN):
        a = max(0, s - CTX); b = min(x.numel(), s + WIN + CTX)
        with torch.inference_mode(): e = torch.log_softmax(model(xn[a:b][None].to(dev)).logits[0].float(), -1)
        r = e.size(0) / ((b - a) / HOP); f0 = int(round((s - a) / HOP * r)); f1 = int(round((min(s + WIN, x.numel()) - a) / HOP * r)); ems.append(e[f0:f1])
    em = torch.cat(ems); ratio = x.numel() / em.size(0) / SR
    raw, lineof = [], []
    for k, ln in enumerate(JOB["lines"]):
        for w in ln.split(): raw.append(w); lineof.append(k)
    rom = [norm(U.romanize_string(w)) for w in raw]; toks, owner = [], []
    for i, w in enumerate(rom):
        for c in w: toks.append(V[c]); owner.append(i)
    Tn, N = em.size(0), len(toks); tg = torch.tensor(toks, device=dev)
    prev = torch.full((N + 1,), -1e9, device=dev); prev[0] = 0; bp = torch.zeros((Tn, N + 1), dtype=torch.bool, device=dev); eb = em[:, blank]
    for t in range(Tn):
        stay = prev + eb[t]; adv = torch.full_like(stay, -1e9); adv[1:] = prev[:-1] + em[t, tg]; bp[t] = adv > stay; prev = torch.maximum(stay, adv)
    j = N; fr = [0] * N
    for t in range(Tn - 1, -1, -1):
        if j > 0 and bp[t, j]: fr[j - 1] = t; j -= 1
    tm = {}
    for k, i in enumerate(owner): a0, a1 = tm.get(i, (fr[k], fr[k])); tm[i] = (min(a0, fr[k]), max(a1, fr[k]))
    words = []
    for i in range(len(raw)): words.append([tm[i][0] * ratio, (tm[i][1] + 1) * ratio] if i in tm else None)
    for i in range(len(words)):
        if words[i] is None:
            p = next((words[k][1] for k in range(i - 1, -1, -1) if words[k]), 0.0); q = next((words[k][0] for k in range(i + 1, len(words)) if words[k]), D)
            words[i] = [p, max(p + 0.2, q)]
    lines_t = []
    for k in range(len(JOB["lines"])):
        ws = [words[i] for i in range(len(raw)) if lineof[i] == k]; lines_t.append([ws[0][0], ws[-1][1]])
    print("aligned unmatched", j, "lines", [[round(a, 1), round(b, 1)] for a, b in lines_t], flush=True)
    del bp, em, ems, model
    FW = []
    for n, k in enumerate(JOB["face"]):
        a = max(0.0, lines_t[k][0] - 0.15); b = min(D, lines_t[k][1] + 0.25)
        if FW and a - FW[-1][2] < 0.6: FW[-1] = (FW[-1][0], FW[-1][1], b)
        else: FW.append((len(FW), a, b))
    print("face windows", [(round(a, 1), round(b, 1)) for _, a, b in FW], flush=True)
    json.dump({"words": words, "lines_t": lines_t, "FW": FW}, open(f"{T}/align.json", "w"))

    # ---------- 2) LatentSync 1.5 on CPU (pinned to the commit checked on 23 Nov; patched cuda -> cpu, fp32) ----------
    stage("lipsync_setup")
    LS_SHA = "a229c3948406bc2cf6eaf4873e662e70c6a04746"
    sh(f"git clone -q https://github.com/bytedance/LatentSync {LS} && cd {LS} && git -c advice.detachedHead=false checkout -q {LS_SHA}")
    def patch(f, a, b, count=1):
        p = f"{LS}/{f}"; s = open(p).read(); assert s.count(a) >= count, (f, a[:40]); open(p, "w").write(s.replace(a, b))
    patch("scripts/inference.py", 'device="cuda",', 'device="cpu",')
    patch("scripts/inference.py", ').to("cuda")', ').to("cpu")')
    patch("latentsync/pipelines/lipsync_pipeline.py", 'ImageProcessor(height, device="cuda", mask_image=mask_image)', 'ImageProcessor(height, device="cpu", mask_image=mask_image)')
    p = f"{LS}/latentsync/utils/image_processor.py"; s = open(p).read()
    s2 = re.sub(r'if device == "cpu":\n\s+self\.face_detector = None\n\s+else:\n\s+self\.face_detector = FaceDetector\(device=device\)', 'self.face_detector = FaceDetector(device=device)', s)
    assert s2 != s, "image_processor patch"; open(p, "w").write(s2)
    patch("latentsync/utils/face_detector.py", 'providers=["CUDAExecutionProvider"]', 'providers=["CPUExecutionProvider"]')
    patch("latentsync/utils/face_detector.py", "ctx_id=cuda_to_int(device)", "ctx_id=-1")
    patch("latentsync/utils/affine_transform.py", 'device="cpu", dtype=torch.float16)', 'device="cpu", dtype=torch.float32)')
    print("left cuda refs:", subprocess.run(f"cd {LS} && grep -rn '\"cuda\"\\|\\.cuda()\\|\\.half()' scripts/inference.py latentsync/pipelines latentsync/utils/image_processor.py latentsync/utils/face_detector.py latentsync/whisper/audio2feature.py | grep -v 'VideoProcessor(256' | wc -l", shell=True, capture_output=True, text=True).stdout.strip(), flush=True)
    os.chdir(LS)
    for _ in range(5):
        sh("python -c \"from huggingface_hub import hf_hub_download as d; [d('ByteDance/LatentSync-1.5', f, local_dir='checkpoints') for f in ('whisper/tiny.pt', 'latentsync_unet.pt')]\"")
        if os.path.exists("checkpoints/latentsync_unet.pt"): break
        time.sleep(10)
    sh("python -c \"from insightface.app import FaceAnalysis; FaceAnalysis(name='buffalo_l', root='checkpoints/auxiliary', providers=['CPUExecutionProvider'])\"")
    STEPS = JOB.get("steps", 12); DC = "--enable_deepcache " if JOB.get("deepcache", True) else ""
    print("lipsync steps", STEPS, "deepcache", bool(DC), flush=True)
    cx, cy, cs = JOB["face_crop"]; FD = dur(f"{IN}/face.mp4") or 30
    stage("lipsync")
    lip = {}
    for n, a, b in FW:   # one lane: the runner has 4 vCPU, two parallel processes would only fight for them
        L = b - a; fo = (n * FD / max(1, len(FW)) + 1.3 * n) % max(0.1, FD - L - 1)
        sh(f"ffmpeg -y -loglevel error -ss {a:.3f} -t {L:.3f} -i {T}/v16.wav {T}/fa{n}.wav", quiet=True)
        sh(f"ffmpeg -y -loglevel error -stream_loop -1 -ss {fo:.2f} -i {IN}/face.mp4 -t {L + 0.5:.3f} -vf 'crop={cs}:{cs}:{cx}:{cy},scale=512:512,fps=25' -an -c:v libx264 -crf 12 -preset veryfast -pix_fmt yuv420p {T}/fv{n}.mp4", quiet=True)
        t1 = time.time()
        sh(f"python -m scripts.inference --unet_config_path configs/unet/stage2.yaml --inference_ckpt_path checkpoints/latentsync_unet.pt --inference_steps {STEPS} --guidance_scale 1.5 {DC}--video_path {T}/fv{n}.mp4 --audio_path {T}/fa{n}.wav --video_out_path {T}/fl{n}.mp4")
        lip[n] = {"sec_of_video": round(L, 2), "min": round((time.time() - t1) / 60, 2), "ok": os.path.exists(f"{T}/fl{n}.mp4")}
        print("lip window", n, lip[n], flush=True); STAGES["lip_windows"] = lip; put_json(STAGES, "stages.json")
        if os.path.exists(f"{T}/fl{n}.mp4"): put(f"{T}/fl{n}.mp4", f"face/fl{n}.mp4", "video/mp4")
    os.chdir(T)
    put(f"{T}/align.json", "face/align.json", "application/json")
else:
    # ---------- split design: alignment + face circles were made on a Kaggle GPU (gh_lipsync_kernel.py) -> fetch them ----------
    stage("fetch_face")
    src = JOB.get("face_from", OUT + "face/")
    S3.download_file(BUCKET, src + "align.json", f"{T}/align.json")
    al = json.load(open(f"{T}/align.json")); words, lines_t, FW = al["words"], al["lines_t"], [tuple(x) for x in al["FW"]]
    for n, a, b in FW:
        try: S3.download_file(BUCKET, src + f"fl{n}.mp4", f"{T}/fl{n}.mp4")
        except Exception as e: print("no face clip", n, type(e).__name__, flush=True)
    os.chdir(T)

# ---------- 3) fast-cut background (kernel2 code) ----------
stage("shots")
used = {}; shots = []
_live = {}
def live_len(src):
    if src not in _live:
        cl = dur(src) or 10.0
        o = subprocess.run(f"ffmpeg -hide_banner -i {src} -map 0:v -vf freezedetect=n=0.003:d=0.4 -f null - 2>&1 | grep -o 'freeze_[a-z]*: [0-9.]*'",
                           shell=True, capture_output=True, text=True).stdout.split("\n")
        ev = [x for x in o if x.strip()]
        if ev and ev[-1].startswith("freeze_start"):
            fs = float(ev[-1].split(":")[1]); cl = max(1.0, min(cl, fs + 0.1)) if fs > 1.0 else cl
        _live[src] = cl
    return _live[src]
bounds = [0.0] + [lines_t[k][0] - 0.05 for k in range(1, len(lines_t))] + [D]
for k, beats in enumerate(JOB["beats"]):
    a, b = bounds[k], bounds[k + 1]; n = len(beats); L = (b - a) / n
    for i, bt in enumerate(beats):
        src = f"{IN}/{bt['clip']}"; cl = live_len(src)
        at = bt.get("at")
        if at is None:
            at = used.get(bt["clip"], 0.0)
            if at + L > cl: at = max(0.0, (at + 1.7) % max(0.1, cl - L))
        used[bt["clip"]] = at + L
        shots.append({"src": src, "cl": cl, "at": min(at, max(0, cl - L - 0.05)), "t0": a + i * L, "L": L, "move": bt.get("move", random.choice(["in", "out"])),
                      "hit": bt.get("hit", False), "whoosh": i == 0 and k > 0, "label": bt.get("label")})
print("shots", len(shots), "avg len", round(D / len(shots), 2), flush=True)
parts = []
for i, s in enumerate(shots):
    L = s["L"]; z = 0.09
    zexp = {"in": f"1+{z}*t/{L:.3f}", "out": f"1+{z}-{z}*t/{L:.3f}"}.get(s["move"], f"1+{z}")
    xexp = {"left": f"(iw-ow)*(1-t/{L:.3f})", "right": f"(iw-ow)*t/{L:.3f}"}.get(s["move"], "(iw-ow)/2")
    avail = max(0.3, s["cl"] - s["at"]); fill = ""
    if avail < L:
        f = min(1.5, L / avail); fill = f"setpts={f:.4f}*(PTS-STARTPTS),"
        if avail * f < L - 0.05: fill += "split[fw][bw];[bw]reverse[rv];[fw][rv]concat=n=2:v=1:a=0,"
    vf = (f"{fill}fps=30,scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,setsar=1,tpad=stop_mode=clone:stop_duration=0.3,"
          f"scale=w='trunc(1080*({zexp})/2)*2':h='trunc(1920*({zexp})/2)*2':eval=frame,crop=1080:1920:x='{xexp}':y='(ih-oh)/2',"
          f"eq=contrast=1.07:saturation=1.10:gamma=0.98,vignette=angle=PI/5,trim=duration={L:.3f}")
    sh(f"ffmpeg -y -loglevel error -ss {s['at']:.3f} -t {avail:.3f} -i {s['src']} -vf \"{vf}\" -an -c:v libx264 -crf 16 -preset veryfast -pix_fmt yuv420p {T}/s{i:03d}.mp4", quiet=True)
    parts.append(f"{T}/s{i:03d}.mp4")
open(f"{T}/list.txt", "w").write("\n".join(f"file '{p}'" for p in parts))
sh(f"ffmpeg -y -loglevel error -f concat -safe 0 -i {T}/list.txt -c copy {T}/bg.mp4")
print("background", dur(f"{T}/bg.mp4"), flush=True)
sh(f"ffmpeg -y -loglevel error -f lavfi -i 'anoisesrc=c=pink:d=0.55:a=0.6' -af 'highpass=f=500,lowpass=f=6000,afade=t=in:d=0.38:curve=exp,afade=t=out:st=0.38:d=0.17,volume=0.5' -ar 48000 -ac 2 {T}/whoosh.wav")
sh(f"ffmpeg -y -loglevel error -f lavfi -i 'sine=f=52:d=0.9' -f lavfi -i 'anoisesrc=c=brown:d=0.25:a=0.8' -filter_complex '[0]afade=t=out:st=0.05:d=0.85:curve=exp,volume=1.6[s];[1]lowpass=f=300,afade=t=out:d=0.25[n];[s][n]amix=inputs=2:normalize=0' -ar 48000 -ac 2 {T}/hit.wav")
sfx = [(s["t0"] - 0.3, "whoosh") for s in shots if s["whoosh"]] + [(s["t0"], "hit") for s in shots if s["hit"]]
from PIL import Image, ImageDraw, ImageFont
FONT = "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"   # the font the Kaggle renders use
if not os.path.exists(FONT): FONT = next(iter(glob.glob("/usr/share/fonts/**/*Bold*.ttf", recursive=True)), None)
print("label font", FONT, flush=True)
def label_png(i, lb):
    txt = lb["text"].replace("₹", "Rs "); size = lb.get("size", 70)
    try: f = ImageFont.truetype(FONT, size)
    except Exception: f = ImageFont.load_default(size=size)
    tw, th = f.getbbox(txt)[2], f.getbbox(txt)[3]; pad = 28
    im = Image.new("RGBA", (tw + 2 * pad, th + 2 * pad + (140 if lb.get("arrow") else 0)), (0, 0, 0, 0)); d = ImageDraw.Draw(im)
    d.rounded_rectangle((0, 0, tw + 2 * pad, th + 2 * pad), radius=22, fill=(255, 214, 74, 245), outline=(0, 0, 0, 255), width=5)
    d.text((pad, pad - 4), txt, font=f, fill=(0, 0, 0, 255))
    if lb.get("arrow"):
        cxx = (tw + 2 * pad) // 2; y0 = th + 2 * pad + 6
        d.line((cxx, y0, cxx, y0 + 110), fill=(255, 214, 74, 255), width=14); d.polygon([(cxx - 34, y0 + 92), (cxx + 34, y0 + 92), (cxx, y0 + 138)], fill=(255, 214, 74, 255))
    if lb.get("mirror"):
        from PIL import ImageOps; im = ImageOps.mirror(im)
    p = f"{T}/lab{i}.png"; im.save(p); return p
ok = [n for n, a, b in FW if os.path.exists(f"{T}/fl{n}.mp4")]; print("lip windows ok", ok, "of", len(FW), flush=True)

# ---------- 5) final: labels + face circles + captions + brand + audio (kernel2 code) ----------
stage("final_encode")
R2 = JOB["circle"]; m = Image.new("L", (R2 * 4, R2 * 4), 0); ImageDraw.Draw(m).ellipse((0, 0, R2 * 4 - 1, R2 * 4 - 1), fill=255); m.resize((R2, R2), Image.LANCZOS).save(f"{T}/mask.png")
ring = Image.new("RGBA", (R2 * 4 + 48, R2 * 4 + 48), (0, 0, 0, 0)); ImageDraw.Draw(ring).ellipse((0, 0, R2 * 4 + 47, R2 * 4 + 47), outline=(255, 214, 74, 255), width=36)
ring.resize((R2 + 12, R2 + 12), Image.LANCZOS).save(f"{T}/ring.png")
inputs = [f"{T}/bg.mp4", f"{IN}/logo.png", f"{IN}/wm.png", f"{T}/mask.png", f"{T}/ring.png"]
fc = ["[1:v]scale=150:-1,format=rgba,colorchannelmixer=aa=0.9[logo]",
      "[2:v]scale=520:-1,format=rgba,colorchannelmixer=aa=0.22[wm]",
      "[0:v][wm]overlay=x='40+(W-w-80)*(0.5+0.5*sin(t/9))':y='260+(H-h-900)*(0.5+0.5*sin(t/13+1))'[v0]"]
cur = "[v0]"; idx = 5
for i, s in enumerate(shots):
    lb = s["label"]
    if not lb: continue
    inputs.append(label_png(i, lb)); li = idx; idx += 1; a = s["t0"] + 0.2; b = s["t0"] + s["L"] - 0.05
    x0, y0 = lb.get("pos", ["(W-w)/2", 700])
    fc.append(f"[{li}:v]format=rgba,fade=in:st={a:.3f}:d=0.2:alpha=1[l{i}]")
    fc.append(f"{cur}[l{i}]overlay=x={x0}:y={y0}:enable='between(t,{a:.3f},{b:.3f})'[lv{i}]"); cur = f"[lv{i}]"
HOP = JOB.get("hop", 0)
for k, (n, a, b) in enumerate(FW):
    if n not in ok: continue
    inputs.append(f"{T}/fl{n}.mp4"); fi = idx; idx += 1
    fc.append(f"[{fi}:v]scale={R2}:{R2},format=rgba,setpts=PTS-STARTPTS+{a:.3f}/TB[f{k}]")
    fc.append(f"[3:v]scale={R2}:{R2},format=gray[mk{k}]")
    fc.append(f"[f{k}][mk{k}]alphamerge,fade=in:st={a:.3f}:d=0.2:alpha=1,fade=out:st={max(a, b - 0.2):.3f}:d=0.2:alpha=1[fc{k}]")
    segs = [(a, b)]
    if HOP:
        cuts = [lines_t[i][0] - 0.05 for i in range(len(lines_t)) if a + 1.0 < lines_t[i][0] < b - 1.0][HOP - 1::HOP]
        pts = [a] + cuts + [b]; segs = list(zip(pts[:-1], pts[1:]))
    if len(segs) > 1: fc.append(f"[fc{k}]split={len(segs)}" + "".join(f"[fc{k}_{j}]" for j in range(len(segs))))
    for j, (s0, s1) in enumerate(segs):
        px, py = JOB["positions"][(k + j) % len(JOB["positions"])]
        src = f"[fc{k}_{j}]" if len(segs) > 1 else f"[fc{k}]"
        fc.append(f"{cur}[4:v]overlay=x={px - 6}:y={py - 6}:enable='between(t,{s0:.3f},{s1:.3f})'[r{k}_{j}]")
        fc.append(f"[r{k}_{j}]{src}overlay=x={px}:y={py}:eof_action=pass:enable='between(t,{s0:.3f},{s1:.3f})'[c{k}_{j}]"); cur = f"[c{k}_{j}]"
caps = JOB["caps"]
for k, cp in enumerate(caps):
    a = words[cp["w0"]][0]
    b = words[caps[k + 1]["w0"]][0] if k + 1 < len(caps) else words[cp["w1"]][1] + 0.4
    b = max(b, a + 0.25); inputs.append(f"{IN}/caps/{cp['png']}"); ci = idx; idx += 1
    fc.append(f"{cur}[{ci}:v]overlay=x=(W-w)/2:y={JOB['cap_y']}:enable='between(t,{a:.3f},{b:.3f})'[k{k}]"); cur = f"[k{k}]"
fc.append(f"{cur}[logo]overlay=x=W-w-36:y=120[vout]")
mus = f"{IN}/music.mp3"; ins = " ".join((f"-loop 1 -i {p}" if p.endswith(".png") else f"-i {p}") for p in inputs) + f" -i {T}/voice.wav -stream_loop -1 -i {mus}"
na = len(inputs); ains = [f"[{na}:a]volume=1.0[va]", f"[{na + 1}:a]volume={JOB.get('music_vol', 0.08)},afade=t=out:st={max(0, D - 2):.2f}:d=2[ma]"]
mix = ["[va]", "[ma]"]
for q, (t, kind) in enumerate(sfx):
    ins += f" -i {T}/{kind}.wav"; ms = max(0, int(t * 1000))
    ains.append(f"[{na + 2 + q}:a]volume={0.35 if kind == 'whoosh' else 0.55},adelay={ms}|{ms}[e{q}]"); mix.append(f"[e{q}]")
ains.append(f"{''.join(mix)}amix=inputs={len(mix)}:normalize=0:duration=first,loudnorm=I=-14:TP=-1.5:LRA=11,afade=t=out:st={max(0, D - 0.35):.2f}:d=0.35[aout]")
open(f"{T}/final2.txt", "w").write(";\n".join(fc + ains))
out = f"{W}/{JOB['tag']}.mp4"
sh(f"ffmpeg -y -loglevel error {ins} -filter_complex_script {T}/final2.txt -map '[vout]' -map '[aout]' -t {D:.3f} -r 30 -c:v libx264 -crf 18 -preset medium -pix_fmt yuv420p -c:a aac -b:a 160k -movflags +faststart {out}")
print("final", dur(out), os.path.getsize(out) if os.path.exists(out) else 0, flush=True)

stage("upload_preview")
put(out, os.path.basename(out), "video/mp4")
fz = subprocess.run(f"ffmpeg -hide_banner -i {out} -map 0:v -vf freezedetect=n=0.002:d=0.5 -f null - 2>&1 | grep -c freeze_start", shell=True, capture_output=True, text=True).stdout.strip()
print("freeze scan:", fz, "frozen moments", flush=True)
pv = f"{W}/{JOB['tag']}_720.mp4"
sh(f"ffmpeg -y -loglevel error -i {out} -vf scale=720:1280 -c:v libx264 -preset veryfast -crf 25 -c:a aac -b:a 128k -movflags +faststart {pv}")
put(pv, os.path.basename(pv), "video/mp4")
put_json({"lines": lines_t, "face": FW, "ok": ok, "freezes": fz, "shots": [[round(s["t0"], 2), round(s["L"], 2), os.path.basename(s["src"])] for s in shots]}, "timing.json")

# ---------- 6) check against the Kaggle render (job.ref, read-only): probe, SSIM over the whole video, frames side by side ----------
if JOB.get("ref"):
    stage("compare")
    ref = f"{W}/ref.mp4"; S3.download_file(BUCKET, JOB["ref"], ref)
    def probe(p): return json.loads(subprocess.run(f"ffprobe -v error -show_entries stream=codec_type,width,height,r_frame_rate,nb_frames,bit_rate:format=duration,size -of json {p}", shell=True, capture_output=True, text=True).stdout)
    cmp = {"gh": probe(out), "kaggle": probe(ref)}
    sh(f"ffmpeg -loglevel error -i {out} -i {ref} -lavfi '[0:v]setpts=PTS-STARTPTS[a];[1:v]setpts=PTS-STARTPTS[b];[a][b]ssim=stats_file={T}/ssim.txt' -f null -")
    per = []
    for l in open(f"{T}/ssim.txt"):
        mm = re.search(r"n:(\d+).*All:([0-9.]+)", l)
        if mm: per.append((int(mm.group(1)), float(mm.group(2))))
    def mean(v): return round(sum(v) / len(v), 4) if v else None
    inface = lambda fr: any(a <= (fr - 1) / 30 <= b for _, a, b in FW if _ in ok)
    cmp["ssim_all"] = mean([v for _, v in per]); cmp["ssim_face_windows"] = mean([v for f, v in per if inface(f)]); cmp["ssim_rest"] = mean([v for f, v in per if not inface(f)])
    cmp["ssim_min"] = min(per, key=lambda x: x[1]) if per else None
    tms = [2.0] + [round((a + b) / 2, 2) for _, a, b in FW] + [10.0, 30.0]
    for t in tms:
        sh(f"ffmpeg -y -loglevel error -ss {t} -i {out} -ss {t} -i {ref} -filter_complex '[0:v][1:v]hstack,scale=1080:-2' -frames:v 1 -q:v 3 {T}/cmp_{t:05.2f}.jpg")
        if os.path.exists(f"{T}/cmp_{t:05.2f}.jpg"): put(f"{T}/cmp_{t:05.2f}.jpg", f"cmp/cmp_{t:05.2f}.jpg", "image/jpeg")
    cmp["frames_at"] = tms; put_json(cmp, "cmp/compare.json")
    print("compare: ssim all", cmp["ssim_all"], "face", cmp["ssim_face_windows"], "rest", cmp["ssim_rest"], flush=True)
stage(None)
print("RESULT DONE", f"{(time.time() - T0) / 60:.1f} min", json.dumps({k: v for k, v in STAGES.items() if not k.startswith("_now")}), flush=True)
