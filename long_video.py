# BuBu TV long non-stop videos, Zuzu Banana pattern (owner 6-7 Nov 2026). One GitHub job per language channel:
#   python long_video.py <code>     env: DAY (0,1,2.. -> title style + lead rotation), N (videos, default 10), DRY=1 (no upload)
# Zuzu (checked 7 Nov, 96 videos): 8 famous songs only; every video = a famous lead song first + the others repeated to 26-45 min;
# 8 uploads a day exactly 1 h apart; title "<native> | <Roman> & More Non-Stop ..." with a new title style each day; the SAME 28 tags on
# every video (channel, generic kids words, every song name); same long description listing all songs + hashtags; no timestamps.
# Each video is uploaded PRIVATE with publishAt (1 h gaps), so it goes public by itself. Re-runs never duplicate (exact title check).
import datetime, json, os, random, re, subprocess, sys, unicodedata
code = sys.argv[1]; DAY = int(os.environ.get("DAY") or 0); N = int(os.environ.get("N") or 10); DRY = os.environ.get("DRY") == "1"
S = json.load(open("data/long/sources.json", encoding="utf-8")); NAME = S["name"]; L = NAME[code].capitalize()
FAMOUS = ["S14_moon", "S11_puppy_bath", "S16_elephant", "S13_hen_chicks", "S15_rain", "S10_counting_bananas", "S17_crow", "S04_monkey_mangoes",
          "S18_birds", "S09_rainbow_puppy", "S07_bedtime_owl", "S12_school_bag_squirrel", "S08_goat_market", "S03_paper_boats"]   # famous rhymes + our most watched (7 Nov views)
MINS = [32, 38, 42, 35, 45, 30, 40, 36, 44, 33, 39, 41]
STYLE = ["& More Non-Stop Nursery Rhymes | Learning Videos", "Non Stop Rhymes | Popular {L} Kids Songs Collection", "| Popular {L} Nursery Rhymes | Non-Stop Kids Rhymes",
         "& More {L} Children's Songs | A Collection", "& Non-Stop Rhymes | Preschool Learning Videos", "& More | Non-Stop Nursery Rhymes for Children | Kids Songs",
         "| {L} Nursery Rhymes Collection", "| Popular Non-Stop {L} Rhymes | Learning Rhymes for Kids", "| Superhit Non-Stop Kids Rhymes | Nursery Rhymes"]
EXTRA = {"hi": ["Hindi Balgeet", "Bacchon Ke Gane"], "te": ["Telugu Rhymes for Children", "Chinnari Patalu"], "ta": ["Tamil Rhymes for Children", "Kuzhandhai Paadalgal"],
         "kn": ["Kannada Rhymes for Children", "Makkala Haadugalu"], "mr": ["Marathi Balgeet", "Marathi Gani for Kids"], "bn": ["Bangla Chotoder Chora", "Bengali Rhymes for Children"],
         "ur": ["Urdu Nazmein for Kids", "Bachon Ki Nazmein"], "en": ["English Rhymes", "Songs for Toddlers"]}


def sh(c):
    return subprocess.run(c, capture_output=True, text=True)


def dur(p):
    return float(sh(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", p]).stdout.strip() or 0)


def roman(s):
    t = S["songs"][s].get("roman", {}).get(code) or s[4:].replace("_", " ").title()
    t = re.split(r"[,،]", t)[0]   # first phrase only: "Vana Vana Vallappa"
    return unicodedata.normalize("NFKD", t).encode("ascii", "ignore").decode().strip(" ?!.,")


def native(s):
    t = re.split(r"[,،]", S["songs"][s]["title"].get(code) or "")[0]
    t = "".join(ch for ch in t if not unicodedata.category(ch).startswith(("S", "C")) and ch not in "!?.;:\"()[]{}")   # keep vowel signs; drop emoji/punctuation
    return re.sub(r"\s+", " ", t).strip()


os.makedirs("lv", exist_ok=True); os.makedirs("norm", exist_ok=True); have = {}
for slug, info in S["songs"].items():
    src = info["src"].get(code)
    if not src: continue
    raw = f"lv/{slug}.mp4"
    if "url" in src:
        sh(["curl", "-sSLf", "--retry", "3", "-o", raw, src["url"]])
    else:
        env = dict(os.environ, KAGGLE_API_TOKEN=os.environ.get(f"KAGGLE_KEY{src['key']}", ""), PYTHONUTF8="1"); d = f"lv/k_{slug}"
        subprocess.run(["kaggle", "kernels", "output", src["kernel"], "-p", d, "--file-pattern", "^" + re.escape(src["file"]) + "$"], env=env, capture_output=True, text=True)
        if os.path.exists(f"{d}/{src['file']}"): os.replace(f"{d}/{src['file']}", raw)
    if not os.path.exists(raw) or os.path.getsize(raw) < 1_000_000:
        print(f"{slug} {code} MISSING source", flush=True); continue
    n = f"norm/{slug}.mp4"   # same size/fps/codec for every song -> lossless join
    r = sh(["ffmpeg", "-y", "-loglevel", "error", "-i", raw, "-vf", "scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2,fps=24,format=yuv420p,setsar=1",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "22", "-c:a", "aac", "-ar", "48000", "-ac", "2", "-b:a", "160k", n])
    os.remove(raw)
    if r.returncode:
        print(slug, "encode failed", r.stderr[-200:], flush=True); continue
    have[slug] = dur(n); print(f"{slug} ok {have[slug]:.0f}s", flush=True)
if len(have) < 6:
    print(f"RESULT {code} NOT_ENOUGH_SONGS {len(have)}"); sys.exit(0)

ALL = [s for s in FAMOUS if s in have] + [s for s in have if s not in FAMOUS]
leads = [ALL[(DAY * 3 + i) % len(ALL)] for i in range(min(N, len(ALL)))]
songs_roman = [roman(s) for s in ALL]
tags, tl = [], 0
for t in ["BuBu TV", f"BuBu TV {L}", f"{L} Rhymes", "Kids Rhymes", "Nursery Rhymes", f"{L} Nursery Rhymes", "Kids Songs", f"{L} Kids Songs", "Baby Songs", "Rhymes for Kids",
          "3D Animation", "Cartoon Rhymes", "Preschool Rhymes", "Toddler Songs", "Children Songs"] + EXTRA.get(code, []) + songs_roman + ["Kids Learning Songs", "Animal Rhymes", "Educational Rhymes"]:
    if t and t not in tags and tl + len(t) + 3 < 490:
        tags.append(t); tl += len(t) + 3
DESC = (f"Welcome to BuBu TV {L}, a happy world of colourful songs, cute characters and fun learning for little ones!\n\n"
        f"Enjoy a non-stop collection of {L} nursery rhymes, kids songs, baby songs and action rhymes that bring smiles to children's faces.\n\n"
        f"Enjoy your favourite {L} rhymes like " + ", ".join(songs_roman[:-1]) + f" and {songs_roman[-1]}.\n\n"
        + " | ".join(native(s) for s in ALL if native(s)) + "\n\n"
        "At BuBu TV we make bright 3D animated songs with a loving family, playful animals and catchy tunes. Every song is a tiny story that teaches sharing, kindness, "
        "counting, colours, good habits and everyday life, for toddlers, preschoolers and young children.\n\nBuBu TV - Happy Songs, Little Stories and Big Smiles!\n\n"
        f"#BuBuTV #{L}Rhymes #KidsRhymes #NurseryRhymes #{L}KidsSongs #KidsSongs #RhymesForKids #BabySongs #3DAnimation #PreschoolSongs #ToddlerSongs #{L}NurseryRhymes")[:4900]

yt, have_t = None, set()
if not DRY:
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload
    c = Credentials.from_authorized_user_info(json.loads(os.environ["YT_TOKEN"]))
    if not c.valid: c.refresh(Request())
    yt = build("youtube", "v3", credentials=c, cache_discovery=False)
    up = yt.channels().list(part="contentDetails", mine=True).execute()["items"][0]["contentDetails"]["relatedPlaylists"]["uploads"]; tok = None
    while True:
        r = yt.playlistItems().list(part="snippet", playlistId=up, maxResults=50, pageToken=tok).execute()
        have_t |= {i["snippet"]["title"].strip() for i in r["items"]}; tok = r.get("nextPageToken")
        if not tok or len(have_t) > 800: break

now = datetime.datetime.now(datetime.timezone.utc); ist = datetime.timezone(datetime.timedelta(hours=5, minutes=30))
first = (now + datetime.timedelta(minutes=100)).astimezone(ist).replace(minute=0, second=0, microsecond=0) + datetime.timedelta(hours=1)
from PIL import Image, ImageDraw, ImageFont
FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
for i, lead in enumerate(leads):
    rnd = random.Random(f"{DAY}-{i}-{code}"); T = MINS[(DAY * 5 + i) % len(MINS)] * 60; seq = [lead]; tot = have[lead]
    while tot < T and len(seq) < 80:
        pool = [s for s in have if s != lead]; rnd.shuffle(pool)
        for s in pool:
            if tot >= T: break
            if s in seq[-4:]: continue
            seq.append(s); tot += have[s]
    out = f"long_{code}_{i}.mp4"; open("list.txt", "w").write("".join(f"file 'norm/{s}.mp4'\n" for s in seq))
    r = sh(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", "list.txt", "-c", "copy", "-movflags", "+faststart", out])
    if r.returncode:
        print(f"RESULT {code} JOIN_FAILED {i} {r.stderr[-150:]}"); continue
    M = round(dur(out) / 60); nat, rom = native(lead), roman(lead); st = STYLE[DAY % len(STYLE)].format(L=L)
    head = rom if code == "en" or not nat or nat.lower() == rom.lower() else f"{nat} | {rom}"
    title = f"{head} {st}"   # native name ALWAYS first (owner 7 Nov); shorten the English tail instead
    for short in ["& More Non-Stop Rhymes | Learning Videos", "& More Non-Stop Rhymes", "Non-Stop Rhymes"]:
        if len(title) <= 100: break
        title = f"{head} {short}"
    if len(title) > 100: title = f"{nat} {short}"[:100]
    th = f"thumb_{code}_{i}.jpg"; base = f"data/songs/{lead}/thumb_{code}.jpg"
    if os.path.exists(base):
        im = Image.open(base).convert("RGB").resize((1280, 720))
    else:   # famous rhymes have no thumbnail file yet -> a bright frame from the song
        sh(["ffmpeg", "-y", "-loglevel", "error", "-ss", str(int(have[lead] * 0.35)), "-i", f"norm/{lead}.mp4", "-frames:v", "1", "-vf", "scale=1280:720", th])
        im = Image.open(th).convert("RGB")
    d = ImageDraw.Draw(im); f = ImageFont.truetype(FONT, 60); txt = f"{M} MIN NON-STOP"
    w = d.textlength(txt, font=f); d.rounded_rectangle([1280 - w - 60, 20, 1260, 106], 24, fill=(230, 30, 60)); d.text((1280 - w - 40, 28), txt, font=f, fill="white")
    f2 = ImageFont.truetype(FONT, 54); w2 = d.textlength(rom[:28], font=f2)
    d.rounded_rectangle([20, 720 - 106, 60 + w2, 700], 24, fill=(255, 205, 0)); d.text((40, 720 - 98), rom[:28], font=f2, fill=(40, 20, 80)); im.save(th, quality=90)
    slot = first + datetime.timedelta(hours=i); pub = slot.astimezone(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    print(f"[{i}] {title} | {M} min | {len(seq)} songs | {slot:%H:%M} IST | " + " > ".join(roman(s) for s in seq), flush=True)
    if DRY:
        os.remove(out); continue
    if title in have_t:
        print(f"RESULT {code} ALREADY_THERE {title}"); os.remove(out); continue
    yl = code if code in ("hi", "te", "ta", "kn", "mr", "bn", "en", "ur", "ml", "gu", "pa", "or", "as", "ne") else None
    sn = {"title": title, "description": DESC, "tags": tags, "categoryId": "22"}
    if yl: sn.update({"defaultLanguage": yl, "defaultAudioLanguage": yl})
    body = {"snippet": sn, "status": {"privacyStatus": "private", "publishAt": pub, "selfDeclaredMadeForKids": True, "embeddable": True, "containsSyntheticMedia": True}}
    try:
        req = yt.videos().insert(part="snippet,status", body=body, media_body=MediaFileUpload(out, chunksize=32 * 2**20, resumable=True)); res = None
        while res is None: _, res = req.next_chunk()
    except Exception as e:
        print(f"RESULT {code} STOPPED at {i} {str(e)[-200:]}"); break
    os.remove(out); vid = res["id"]
    try:
        yt.thumbnails().set(videoId=vid, media_body=MediaFileUpload(th, mimetype="image/jpeg")).execute(); t = "thumb ok"
    except Exception as e:
        t = "thumb FAILED " + str(e)[-80:]
    print(f"RESULT {code} SCHEDULED {i} {vid} {slot:%H:%M} IST {M} min lead {lead} {t}", flush=True)
