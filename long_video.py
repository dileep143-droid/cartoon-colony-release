# BuBu TV long non-stop videos, Zuzu Banana pattern (owner 6-7 Nov 2026). One GitHub job per language channel:
#   python long_video.py <code>     env: DAY (0,1,2.. -> title style + lead rotation), N (videos, default 10), DRY=1 (no upload)
# Zuzu (checked 7 Nov, 96 videos): 8 famous songs only; every video = a famous lead song first + the others repeated to 26-45 min;
# 8 uploads a day exactly 1 h apart; title "<native> | <Roman> & More Non-Stop ..." with a new title style each day; the SAME 28 tags on
# every video (channel, generic kids words, every song name); same long description listing all songs + hashtags; no timestamps.
# Each video is uploaded PRIVATE with publishAt (1 h gaps), so it goes public by itself. Re-runs never duplicate (exact title check).
import datetime, json, os, random, re, subprocess, sys, unicodedata, zlib
code = sys.argv[1]
DAY = int(os.environ.get("DAY") or 0) if (os.environ.get("DAY") or "").strip() else (datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=5, minutes=30))).date() - datetime.date(2026, 11, 7)).days; N = int(os.environ.get("N") or 3); DRY = os.environ.get("DRY") == "1"
S = json.load(open("data/long/sources.json", encoding="utf-8")); NAME = S["name"]; L = NAME[code].capitalize()
FAMOUS = ["S14_moon", "S11_puppy_bath", "S16_elephant", "S13_hen_chicks", "S15_rain", "S10_counting_bananas", "S17_crow", "S04_monkey_mangoes",
          "S18_birds", "S09_rainbow_puppy", "S07_bedtime_owl", "S12_school_bag_squirrel", "S08_goat_market", "S03_paper_boats"]   # famous rhymes + our most watched (7 Nov views)
MINS = [32, 38, 42, 35, 45, 30, 40, 36, 44, 33, 39, 41]
STYLE = ["& Many More Non-Stop Popular {L} Rhymes For Kids", "& More Non-Stop {L} Rhymes For Kids | Learning Videos", "| Popular {L} Nursery Rhymes For Kids | Non-Stop",
         "& More {L} Kids Songs | Non-Stop {L} Rhymes", "& Many More {L} Rhymes For Children | Non-Stop Collection", "| Non-Stop {L} Rhymes For Kids | Baby Songs",
         "& More Superhit {L} Rhymes For Kids", "| {L} Nursery Rhymes Collection For Kids", "& More Popular {L} Kids Rhymes | Non-Stop"]   # 7 Nov owner: the LANGUAGE word in every title (people search "telugu rhymes")
TOPIC = json.load(open("data/long/topics.json", encoding="utf-8")) if os.path.exists("data/long/topics.json") else {}
NATKW = {"hi": ["हिंदी कविता", "बालगीत", "बच्चों के गाने", "हिंदी राइम्स"], "te": ["తెలుగు రైమ్స్", "చిన్నారి పాటలు", "పిల్లల పాటలు"], "ta": ["தமிழ் ரைம்ஸ்", "குழந்தை பாடல்கள்"],
         "kn": ["ಕನ್ನಡ ರೈಮ್ಸ್", "ಮಕ್ಕಳ ಹಾಡುಗಳು"], "mr": ["मराठी बालगीत", "मुलांची गाणी"], "bn": ["বাংলা ছড়া", "ছোটদের গান"], "ur": ["اردو نظمیں", "بچوں کی نظمیں"], "en": []}
EXTRA = {"hi": ["Hindi Balgeet", "Bacchon Ke Gane"], "te": ["Telugu Rhymes for Children", "Chinnari Patalu"], "ta": ["Tamil Rhymes for Children", "Kuzhandhai Paadalgal"],
         "kn": ["Kannada Rhymes for Children", "Makkala Haadugalu"], "mr": ["Marathi Balgeet", "Marathi Gani for Kids"], "bn": ["Bangla Chotoder Chora", "Bengali Rhymes for Children"],
         "ur": ["Urdu Nazmein for Kids", "Bachon Ki Nazmein"], "en": ["English Rhymes", "Songs for Toddlers"]}


def sh(c):
    return subprocess.run(c, capture_output=True, text=True)


def dur(p):
    return float(sh(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", p]).stdout.strip() or 0)


def phrase(t):   # 7 Nov: join comma parts until >= 3 words
    out = []
    for part in re.split(r"[,،]", t):
        out += part.split()
        if len(out) >= 3: break
    return " ".join(out)


def roman(s):
    t = S["songs"][s].get("roman", {}).get(code) or s[4:].replace("_", " ").title()
    t = phrase(t)   # first phrase: "Vana Vana Vallappa", but "Rain Rain Go Away" (not just "Rain")
    return unicodedata.normalize("NFKD", t).encode("ascii", "ignore").decode().strip(" ?!.,")


def native(s):
    t = phrase(S["songs"][s]["title"].get(code) or "")
    t = "".join(ch for ch in t if not unicodedata.category(ch).startswith(("S", "C")) and ch not in "!?.;:\"()[]{}")   # keep vowel signs; drop emoji/punctuation
    return re.sub(r"\s+", " ", t).strip()


os.makedirs("lv", exist_ok=True); os.makedirs("norm", exist_ok=True); have = {}
LOGO = "data/long/logo.png"
DRV = DROOT = None; DFOLD = {}   # 9 Nov owner: songs come from Google Drive 'BuBu TV Songs/<slug>/<file>' (same names as the Kaggle output); Kaggle only as fallback
if os.environ.get("DRIVE_TOKEN"):
    try:
        from google.oauth2.credentials import Credentials
        from google.auth.transport.requests import Request
        from googleapiclient.discovery import build as _dbuild
        _c = Credentials.from_authorized_user_info(json.loads(os.environ["DRIVE_TOKEN"]))
        if not _c.valid: _c.refresh(Request())
        DRV = _dbuild("drive", "v3", credentials=_c, cache_discovery=False)
        _r = DRV.files().list(q="name='BuBu TV Songs' and mimeType='application/vnd.google-apps.folder' and trashed=false", fields="files(id)").execute()["files"]
        DROOT = _r[0]["id"] if _r else None
    except Exception as e:
        print("DRIVE NOT AVAILABLE", str(e)[-150:], flush=True); DRV = None


def drive_get(slug, fname, out):
    if not DRV or not DROOT or not fname: return False
    try:
        if slug not in DFOLD:
            f = DRV.files().list(q=f"name='{slug}' and '{DROOT}' in parents and mimeType='application/vnd.google-apps.folder' and trashed=false", fields="files(id)").execute()["files"]
            DFOLD[slug] = {x["name"]: x["id"] for x in DRV.files().list(q=f"'{f[0]['id']}' in parents and trashed=false", fields="files(id,name)", pageSize=1000).execute()["files"]} if f else {}
        fid = DFOLD[slug].get(fname)
        if not fid: return False
        from googleapiclient.http import MediaIoBaseDownload
        with open(out, "wb") as fh:
            d = MediaIoBaseDownload(fh, DRV.files().get_media(fileId=fid), chunksize=64 * 2**20); done = False
            while not done: _, done = d.next_chunk(num_retries=5)
        return os.path.getsize(out) > 1_000_000
    except Exception as e:
        print(slug, fname, "drive failed", str(e)[-150:], flush=True)
        if os.path.exists(out): os.remove(out)
        return False


for slug, info in S["songs"].items():
    src = info["src"].get(code)
    if not src: continue
    raw = f"lv/{slug}.mp4"
    if "url" in src:
        sh(["curl", "-sSLf", "--retry", "3", "-o", raw, src["url"]])
    elif drive_get(slug, src.get("file"), raw):
        print(f"SOURCE {slug} {code} drive", flush=True)
    else:
        env = dict(os.environ, KAGGLE_API_TOKEN=os.environ.get(f"KAGGLE_KEY{src['key']}", ""), PYTHONUTF8="1"); d = f"lv/k_{slug}"
        subprocess.run(["kaggle", "kernels", "output", src["kernel"], "-p", d, "--file-pattern", "^" + re.escape(src["file"]) + "$"], env=env, capture_output=True, text=True)
        if os.path.exists(f"{d}/{src['file']}"): os.replace(f"{d}/{src['file']}", raw); print(f"SOURCE {slug} {code} kaggle fallback", flush=True)
    if not os.path.exists(raw) or os.path.getsize(raw) < 1_000_000:
        print(f"{slug} {code} MISSING source", flush=True); continue
    n = f"norm/{slug}.mp4"   # same size/fps/codec for every song -> lossless join
    base = "scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2,fps=24,setsar=1"
    if os.path.exists(LOGO):   # 8 Nov owner: our BuBu TV logo in the top-right corner of every long video
        vf = ["-i", LOGO, "-filter_complex", f"[0:v]{base}[v];[1:v]scale=150:150,format=rgba,colorchannelmixer=aa=0.92[l];[v][l]overlay=W-w-36:32,format=yuv420p[o]", "-map", "[o]", "-map", "0:a?"]
    else: vf = ["-vf", base + ",format=yuv420p"]
    r = sh(["ffmpeg", "-y", "-loglevel", "error", "-i", raw] + vf +
           ["-c:v", "libx264", "-preset", "veryfast", "-crf", "22", "-c:a", "aac", "-ar", "48000", "-ac", "2", "-b:a", "160k", n])
    os.remove(raw)
    if r.returncode:
        print(slug, "encode failed", r.stderr[-200:], flush=True); continue
    have[slug] = dur(n); print(f"{slug} ok {have[slug]:.0f}s", flush=True)
if len(have) < 6:
    print(f"RESULT {code} NOT_ENOUGH_SONGS {len(have)}"); sys.exit(0)

ALL = [s for s in FAMOUS if s in have] + [s for s in have if s not in FAMOUS]
# 8 Nov owner: new songs (sources "new") are ADD-ONS - mixed into every video like the others. Lead (starting) songs: first finish the old round
# (every old song leads at least once: day 0 + 1 used the old window, day 2 = the old songs not led yet), THEN the new songs lead one by one
# (random order, same for every channel), then everything rotates.
OLD = [s for s in ALL if not S["songs"][s].get("new")]; NEW = [s for s in ALL if S["songs"][s].get("new")]
LASTP = {}; PREV = {}   # how many times each of today's lead songs already led on this channel (picks a different title pattern each time)
H10 = 10   # 6-9 Nov runs uploaded 10 long videos per channel per day; from 10 Nov N per day (owner 9 Nov: 3 long + 2 two-minute songs)
def old_window(d): return [OLD[(d * 3 + i) % len(OLD)] for i in range(min(H10, len(OLD)))]
def day_start(d): return 0 if d <= 2 else H10 + (d - 3) * N          # where day d starts in the lead queue Q (day 2 = 9 Nov = first 10)
def day_end(d): return day_start(d) + (H10 if d == 2 else N)
if DAY < 2 or not NEW:
    leads = old_window(DAY) if OLD else ALL[:N]
else:
    led = set(old_window(0)) | set(old_window(1)); nr = NEW[:]; random.Random("new-songs-2026-11-08").shuffle(nr)
    Q = [s for s in OLD if s not in led] + nr
    Q += [s for s in ALL if s not in Q and s not in led and s != 'S11_puppy_bath']   # 9 Nov owner: EVERY song leads once before any song repeats
    cyc = 0   # 9 Nov owner: no song may lead again on the next day -> after the first round, every song leads once per shuffled cycle
    while len(Q) < day_end(DAY) + len(ALL) + 4 * N:
        c = sorted(ALL); random.Random(f"cycle-{cyc}-{code}").shuffle(c); cyc += 1
        tail = set(Q[-max(N, 10):]); c = [x for x in c if x not in tail] + [x for x in c if x in tail]   # songs that just led go to the end of the cycle
        Q += c
    LOOK = [{"S03_paper_boats", "S09_rainbow_puppy", "S11_puppy_bath"}, {"S04_monkey_mangoes", "S18_birds"}]   # same courtyard / same mango tree
    mate = lambda a, b: a == b or any(a in g and b in g for g in LOOK)
    days = [(day_start(d), day_end(d)) for d in range(2, 10**6) if day_end(d) <= len(Q)]
    for k in range(1, len(days)):   # repair: a song from yesterday, twice today, or a look-alike today is swapped with a later free song
        (p0, p1), (b0, b1) = days[k - 1], days[k]
        for j in range(b0, b1):
            bad = lambda x: x in Q[p0:p1] or any(mate(x, y) for y in Q[b0:j])
            if bad(Q[j]):
                for m in range(b1, len(Q)):
                    md = next((i for i, (x0, x1) in enumerate(days) if x0 <= m < x1), None)
                    near = Q[days[md - 1][0]:days[min(md + 1, len(days) - 1)][1]] if md else []
                    if not bad(Q[m]) and Q[j] not in near:
                        Q[j], Q[m] = Q[m], Q[j]; break
    leads = Q[day_start(DAY):day_start(DAY) + (H10 if DAY == 2 else N)]
    leads = list(dict.fromkeys(leads)) + [s for s in ALL if s not in leads][:max(0, len(leads) - len(set(leads)))]
    HIST = old_window(0) + old_window(1) + (['S11_puppy_bath'] if 'S11_puppy_bath' in ALL else [])   # 6-8 Nov leads (ep0 + day 0 + day 1)
    PREV.update({s: Q[:day_start(DAY)].count(s) + HIST.count(s) for s in leads})
HOOKS = json.load(open("data/long/hooks.json", encoding="utf-8")) if os.path.exists("data/long/hooks.json") else {}


def make_title(lead, M, nat, rom, head, tpp, st):
    """9 Nov owner: Zuzu-style writing - every time a song leads again its title OPENS differently (famous line / name / topic /
    kids keyword, in turn) and uses a different ending. Every title keeps the language word (7 Nov); non-English = native script first."""
    nz = lambda x: re.sub(r"[\W_]+", "", (x or "").lower())
    hook = (HOOKS.get(lead, {}).get(code) or "").strip()
    if code == "en" and hook: hook = hook[:1].upper() + hook[1:]
    nm = nat or rom
    tpc = (TOPIC.get(lead, {}).get(code) or "").strip()                     # "बंदर का गाना" / "Monkey Song"
    kw = (NATKW.get(code) or EXTRA.get(code) or [f"{L} Rhymes"])[0]          # "हिंदी कविता" / "English Rhymes"
    opens = []
    for o in (hook, nm, tpc, kw):
        if o and nz(o) and nz(o) not in [nz(x) for x in opens]: opens.append(o)
    ends = ["{R} & Many More Best {L} Nursery Rhymes For Kids", "{L} Nursery Rhymes | Kids Non-Stop Learning Videos",
            "Superhit {L} Rhymes For Kids | {M} Min Non-Stop", "{R} & More {L} Kids Songs", "Kids Favourite {L} Rhymes Collection 2026",
            "{M} Min Non-Stop {L} Kids Songs | BuBu TV", "{R} | Preschool Learning Songs in {L} For Kids", "Popular {L} Rhymes For Kids | Non-Stop"]
    def build(parts, end, with_rom):
        r = rom if with_rom and nz(rom) not in nz(" ".join(parts)) else ""
        e = end.format(R=r, L=L, M=M).strip()
        e = re.sub(r"^\| ", "", e) if not r else e
        t = " | ".join(parts) + (" " if e.startswith("&") else " | ") + e
        return re.sub(r"\s+", " ", t).strip()
    n = PREV.get(lead, 0); h = zlib.crc32(lead.encode())
    for oi in range(len(opens)):              # the opening is fixed by how often the song led; only if every ending fails, try the next one
        op = opens[(n + oi) % len(opens)]   # 1st time a song leads: its famous line (Zuzu), then name, topic, keyword
        parts = [op] + ([nm] if nz(nm) not in nz(op) and (op in (tpc, kw) or code != "en") else [])
        for ei in range(len(ends)):
            end = ends[(n * 3 + h + ei) % len(ends)]
            for t in (build(parts, end, True), build(parts, end, False), build([op], end, op not in (tpc, kw)) if op not in (tpc, kw) else ""):
                if t and len(t) <= 100 and t not in have_t and L.lower() in t.lower():
                    LASTP[lead] = op; return t
    return next((t for t in [f"{head} & More {L} Rhymes For Kids", f"{head} {L} Rhymes For Kids", f"{head} {L} Rhymes"] if len(t) <= 100), f"{nat} {L} Rhymes"[:100])


songs_roman = [roman(s) for s in ALL]
tags, tl = [], 0
for t in ["BuBu TV", f"BuBu TV {L}", f"{L} Rhymes", f"{L} Rhymes For Kids"] + NATKW.get(code, []) + [ "Kids Rhymes", "Nursery Rhymes", f"{L} Nursery Rhymes", "Kids Songs", f"{L} Kids Songs", "Baby Songs", "Rhymes for Kids",
          "3D Animation", "Cartoon Rhymes", "Preschool Rhymes", "Toddler Songs", "Children Songs"] + EXTRA.get(code, []) + songs_roman + [native(x) for x in ALL[:6] if native(x) and native(x) != roman(x)] + ["Kids Learning Songs", "Animal Rhymes", "Educational Rhymes"]:
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
six = now.astimezone(ist).replace(hour=int(os.environ.get("START_IST") or 6), minute=0, second=0, microsecond=0)
if six > now + datetime.timedelta(minutes=40): first = six   # nightly run: first video public at 06:00 IST like Zuzu, then every hour
from PIL import Image, ImageDraw, ImageFont
import math
from PIL import ImageFilter as _IF


def minutes_badge(im, M, font="data/long/fonts/LilitaOne-Regular.ttf"):
    """BuBu TV long-video thumbnail badge (owner 9 Nov): sunburst '<M> MIN' + 'NON-STOP' ribbon, bottom-left (title is top, logo bottom-right)."""
    S = 2; W = 360 * S; B = Image.new("RGBA", (W, W), (0, 0, 0, 0)); d = ImageDraw.Draw(B); c = W / 2
    def star(r1, r2, n=18, rot=0):
        return [(c + (r1 if i % 2 == 0 else r2) * math.cos(math.pi * i / n + rot), c + (r1 if i % 2 == 0 else r2) * math.sin(math.pi * i / n + rot)) for i in range(2 * n)]
    d.polygon(star(160 * S, 140 * S), fill=(255, 255, 255, 255))                 # white outer rim
    d.polygon(star(150 * S, 130 * S), fill=(58, 13, 74, 255))                    # dark purple edge (same as the title text stroke)
    d.polygon(star(142 * S, 123 * S), fill=(255, 196, 0, 255))                   # orange-yellow burst
    d.ellipse([c - 112 * S, c - 112 * S, c + 112 * S, c + 112 * S], fill=(255, 230, 40, 255))   # bright yellow centre
    for a in range(18):                                                          # soft rays
        t = math.pi * 2 * a / 18; d.line([(c + 40 * S * math.cos(t), c + 40 * S * math.sin(t)), (c + 108 * S * math.cos(t), c + 108 * S * math.sin(t))], fill=(255, 245, 140, 255), width=10 * S)
    num = str(M); fs = 150 if len(num) <= 2 else 120
    f1 = ImageFont.truetype(font, fs * S); f2 = ImageFont.truetype(font, 46 * S); f3 = ImageFont.truetype(font, 50 * S)
    d.text((c, c - 22 * S), num, font=f1, anchor="mm", fill=(232, 25, 60, 255), stroke_width=9 * S, stroke_fill=(255, 255, 255, 255))
    d.text((c, c + 58 * S), "MIN", font=f2, anchor="mm", fill=(58, 13, 74, 255), stroke_width=5 * S, stroke_fill=(255, 255, 255, 255))
    R = Image.new("RGBA", (W, W), (0, 0, 0, 0)); r = ImageDraw.Draw(R)          # ribbon
    y0, y1 = c + 92 * S, c + 160 * S; x0, x1 = c - 150 * S, c + 150 * S
    r.polygon([(x0 - 26 * S, y0 + 10 * S), (x0 + 6 * S, y0 + 10 * S), (x0 + 6 * S, y1 + 10 * S), (x0 - 26 * S, y1 + 10 * S), (x0 - 10 * S, (y0 + y1) / 2 + 10 * S)], fill=(150, 10, 60, 255))
    r.polygon([(x1 + 26 * S, y0 + 10 * S), (x1 - 6 * S, y0 + 10 * S), (x1 - 6 * S, y1 + 10 * S), (x1 + 26 * S, y1 + 10 * S), (x1 + 10 * S, (y0 + y1) / 2 + 10 * S)], fill=(150, 10, 60, 255))
    r.rounded_rectangle([x0, y0, x1, y1], 14 * S, fill=(240, 40, 122, 255), outline=(255, 255, 255, 255), width=5 * S)
    r.text((c, (y0 + y1) / 2), "NON-STOP", font=f3, anchor="mm", fill=(255, 255, 255, 255), stroke_width=5 * S, stroke_fill=(58, 13, 74, 255))
    B = Image.alpha_composite(B, R).rotate(8, resample=Image.BICUBIC)
    B = B.resize((W // S, W // S), Image.LANCZOS)
    sh = Image.new("RGBA", B.size, (0, 0, 0, 0)); sh.putalpha(B.getchannel("A").point(lambda v: v * 0.55)); sh = sh.filter(_IF.GaussianBlur(9))
    im = im.convert("RGBA"); x, y = 24, im.height - B.height - 16
    im.alpha_composite(sh, (x + 6, y + 10)); im.alpha_composite(B, (x, y))
    return im.convert("RGB")


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
    tp = TOPIC.get(lead, {}).get("en", "")   # 7 Nov owner: say what the song is ABOUT, as people search it ("Rain Song", "Bath Song")
    if tp and tp.split()[0].lower() in rom.lower(): tp = ""
    tpp = f"| {tp} " if tp else ""
    title = make_title(lead, M, nat, rom, head, tpp, st)
    vt = [x for x in [f"{L} {TOPIC.get(lead, {}).get('en', '')}", TOPIC.get(lead, {}).get("en", ""), TOPIC.get(lead, {}).get(code, "")] if x.strip() and x not in tags]
    vt = list(dict.fromkeys(vt))
    vtags, vl = [], 0
    for t in vt + tags:   # this video's topic words first, then the channel tags (limit ~490 chars)
        if vl + len(t) + 3 < 490: vtags.append(t); vl += len(t) + 3
    th = f"thumb_{code}_{i}.jpg"   # Zuzu style (7 Nov): a clean close-up of the lead song's characters, no text; same picture for every language
    # owner 7 Nov: the lead song's OWN attractive thumbnail in THIS language (big native text, rainbow frame, logo); rhymes: data/long/lthumbs
    pick = [p for p in (f"data/songs/{lead}/thumb_{code}.jpg", f"data/long/lthumbs/{lead}_{code}.jpg", f"data/long/thumbs/{lead}.jpg") if os.path.exists(p)]
    # 9 Nov owner: a song that leads AGAIN gets a different picture: 1st time the designed thumbnail, then its variants v1, v2 ...
    var = [p for p in sorted(__import__("glob").glob(f"data/long/variants/{lead}/{code}_v*.jpg"))]
    if pick and var: pick = [([pick[0]] + var)[PREV.get(lead, 0) % (1 + len(var))]]
    if pick:
        Image.open(pick[0]).convert("RGB").resize((1280, 720)).save(th, quality=92)
    else:
        sh(["ffmpeg", "-y", "-loglevel", "error", "-ss", str(int(have[lead] * 0.35)), "-i", f"norm/{lead}.mp4", "-frames:v", "1", "-vf", "scale=1280:720", th])
    try:   # 9 Nov owner: every long-video thumbnail shows the real length ("<M> MIN NON-STOP" sunburst, bottom-left; title top, logo bottom-right)
        if os.path.exists(th): minutes_badge(Image.open(th).convert("RGB").resize((1280, 720)), M).save(th, quality=92)
    except Exception as e:
        print("badge failed", str(e)[-120:], flush=True)
    slot = first + datetime.timedelta(hours=i); pub = slot.astimezone(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    print(f"[{i}] {title} | {M} min | {len(seq)} songs | {slot:%H:%M} IST | " + " > ".join(roman(s) for s in seq), flush=True)
    if DRY:
        os.remove(out); continue
    if title in have_t:
        print(f"RESULT {code} ALREADY_THERE {title}"); os.remove(out); continue
    yl = code if code in ("hi", "te", "ta", "kn", "mr", "bn", "en", "ur", "ml", "gu", "pa", "or", "as", "ne") else None
    top = (f"{nat} | {rom}" if nat and nat != rom else rom) + f" & more non-stop {L} rhymes for kids ({M} minutes) - " + (TOPIC.get(lead, {}).get("en", "") + " " + TOPIC.get(lead, {}).get(code, "") + " - " if TOPIC.get(lead) else "") + " ".join(NATKW.get(code, [])[:2]) + "\n"
    top += f"#{L}Rhymes #{re.sub(r'[^A-Za-z0-9]', '', rom)} #{L}RhymesForKids\n\n"   # 7 Nov: first lines show in search; first 3 hashtags show above the title
    sn = {"title": title, "description": (top + DESC)[:4900], "tags": vtags, "categoryId": "22"}
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
