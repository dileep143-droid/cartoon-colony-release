# 10 Nov owner: "blind" PDF editing on GitHub - nobody (not Claude, not this public log) sees the document.
# Google Drive "PDF Tools/Edit Inbox":
#   your PDF(s) + a text file "changes.txt": EITHER one change per line (old words => new words)
#   OR a request in plain words ("change the date to today and the amount to 5,500") -> a private AI (Qwen2.5 from Hugging Face, running on GitHub) writes the changes
#   (a file "<pdf name>.txt" is used for that one PDF instead of changes.txt)
# GitHub: finds every place on every page, removes the old words (text AND the picture of them on scans, filled with the paper colour around them),
#   writes the new words in the same size and colour -> "PDF Tools/Edit Done/<name> - edited.pdf"; the original + change files -> "PDF Tools/Edit Originals".
# The log prints only numbers ("file 1: 4 changes on 2 pages"), never names or text. Scanned PDFs: put them through "1 Inbox" (OCR) first.
#   python pdf_edit.py check | run
import io, json, os, re, sys
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload, MediaIoBaseDownload
c = Credentials.from_authorized_user_info(json.loads(os.environ["DRIVE_TOKEN"]))
if not c.valid: c.refresh(Request())
dr = build("drive", "v3", credentials=c, cache_discovery=False)
def folder(nm, parent):
    q = f"name='{nm}' and mimeType='application/vnd.google-apps.folder' and trashed=false and '{parent}' in parents"
    f = dr.files().list(q=q, fields="files(id)").execute().get("files", [])
    return f[0]["id"] if f else dr.files().create(body={"name": nm, "mimeType": "application/vnd.google-apps.folder", "parents": [parent]}, fields="id").execute()["id"]
root = folder("PDF Tools", "root"); inbox, done, orig = folder("Edit Inbox", root), folder("Edit Done", root), folder("Edit Originals", root)
files = dr.files().list(q=f"'{inbox}' in parents and trashed=false", fields="files(id,name,mimeType)", pageSize=100).execute().get("files", [])
pdfs = [f for f in files if f["mimeType"] == "application/pdf"]; txts = {f["name"]: f for f in files if f["name"].lower().endswith(".txt")}
if sys.argv[1] == "check":
    ready = bool(pdfs) and bool(txts)
    open(os.environ["GITHUB_OUTPUT"], "a").write(f"has_work={'true' if ready else 'false'}\n")
    print(f"RESULT inbox: {len(pdfs)} pdf, {len(txts)} change file(s)"); sys.exit(0)
def get(fid):
    b = io.BytesIO(); dl = MediaIoBaseDownload(b, dr.files().get_media(fileId=fid)); ok = False
    while not ok: _, ok = dl.next_chunk()
    return b.getvalue()
MODEL = os.environ.get("AI_MODEL_FILE", "/tmp/model.gguf")
def ai_rules(request, pdf_bytes):
    """Plain-words request -> exact 'old => new' pairs. Qwen2.5 (open model from Hugging Face) runs here on the GitHub machine; nothing goes to an AI company.
    Every pair is checked: the old words must really be in the PDF. Nothing is printed."""
    import datetime, pymupdf as fz
    from llama_cpp import Llama
    text = "\n".join(p.get_text() for p in fz.open(stream=pdf_bytes, filetype="pdf"))[:12000]
    today = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=5, minutes=30))).date()
    llm = Llama(model_path=MODEL, n_ctx=8192, n_threads=4, verbose=False)
    msg = [{"role": "system", "content": "You edit documents. Given a document's text and a request, output ONLY JSON: {\"changes\": [{\"old\": \"exact text copied from the document\", \"new\": \"replacement\"}]}. "
            "Copy 'old' exactly as written in the document (same spacing, punctuation and date format). Write 'new' in the same style and date format as 'old'. Include every place the request applies to. No explanations."},
           {"role": "user", "content": f"Today's date is {today:%d %B %Y} ({today:%d/%m/%Y}).\nREQUEST: {request.strip()}\n\nDOCUMENT TEXT:\n{text}"}]
    out = llm.create_chat_completion(messages=msg, temperature=0, max_tokens=800, response_format={"type": "json_object"})["choices"][0]["message"]["content"]
    pairs = json.loads(out).get("changes", [])
    flat = re.sub(r"\s+", " ", text)
    def as_date(old):   # today written in the SAME style as the old date
        M = "January February March April May June July August September October November December".split()
        m = re.search(r"\b(\d{1,2})([./-])(\d{1,2})\2(\d{2,4})\b", old)
        if m: return old[:m.start()] + f"{today.day:02d}{m.group(2)}{today.month:02d}{m.group(2)}{today.year if len(m.group(4)) == 4 else str(today.year)[2:]}" + old[m.end():]
        m = re.search(r"\b(\d{4})([./-])(\d{1,2})\2(\d{1,2})\b", old)
        if m: return old[:m.start()] + f"{today.year}{m.group(2)}{today.month:02d}{m.group(2)}{today.day:02d}" + old[m.end():]
        m = re.search(r"\b(\d{1,2})(st|nd|rd|th)?\s+([A-Za-z]+)\.?,?\s+(\d{4})\b", old)
        if m and m.group(3)[:3].lower() in [x[:3].lower() for x in M]:
            mon = M[today.month - 1] if len(m.group(3)) > 3 else M[today.month - 1][:3]
            return old[:m.start()] + f"{today.day} {mon} {today.year}" + old[m.end():]
        m = re.search(r"\b([A-Za-z]+)\.?\s+(\d{1,2}),?\s+(\d{4})\b", old)
        if m and m.group(1)[:3].lower() in [x[:3].lower() for x in M]:
            mon = M[today.month - 1] if len(m.group(1)) > 3 else M[today.month - 1][:3]
            return old[:m.start()] + f"{mon} {today.day}, {today.year}" + old[m.end():]
        return None
    def core(o, nw):   # keep only the part that really changes ("Name: Ravi Kumar" -> "Ravi Kumar"), so it is changed everywhere it appears
        a, b = o.split(" "), nw.split(" ")
        while len(a) > 1 and len(b) > 1 and a[0] == b[0]: a, b = a[1:], b[1:]
        while len(a) > 1 and len(b) > 1 and a[-1] == b[-1]: a, b = a[:-1], b[:-1]
        extra = a[len(b):]   # words the AI dropped that the request never mentioned are kept ("Rs 4,000 per month" -> "Rs 5,500 per month")
        if extra and not any(w.lower().strip(".,") in request.lower() for w in extra): b = b + extra
        return " ".join(a), " ".join(b)
    good = []
    for c in pairs:
        o, nw = str(c.get("old", "")).strip(), str(c.get("new", "")).strip()
        if re.search(r"\btoday\b", nw, re.I) or (re.search(r"\btoday\b", request, re.I) and re.search(r"\d", o) and as_date(o) and not re.search(r"\d", nw)):
            nw = as_date(o) or nw
        o, nw = core(o, nw)
        if o and o != nw and re.sub(r"\s+", " ", o) in flat and (o, nw) not in good: good.append((o, nw))
    if re.search(r"\b(dates|both dates|all dates|every date|each date)\b", request, re.I) and re.search(r"\btoday\b", request, re.I):   # "all dates to today": catch any the AI missed
        for m in re.finditer(r"\b\d{1,2}([./-])\d{1,2}\1\d{2,4}\b|\b\d{1,2}(?:st|nd|rd|th)?\s+[A-Za-z]{3,9}\.?,?\s+\d{4}\b|\b[A-Za-z]{3,9}\.?\s+\d{1,2},?\s+\d{4}\b", flat):
            nd = as_date(m.group(0))
            if nd and nd != m.group(0) and not any(o == m.group(0) for o, _ in good): good.append((m.group(0), nd))
    return good
def rules_from(raw):
    out = []
    for line in raw.decode("utf-8-sig", "ignore").splitlines():
        if "=>" in line:
            a, b = line.split("=>", 1); a, b = a.strip(), b.strip()
            if a: out.append((a, b))
    return out
import pymupdf as fitz
FONTDIR = "/usr/share/fonts/truetype/noto"
SCRIPTS = [(0x0900, 0x097F, "NotoSansDevanagari"), (0x0980, 0x09FF, "NotoSansBengali"), (0x0A00, 0x0A7F, "NotoSansGurmukhi"), (0x0A80, 0x0AFF, "NotoSansGujarati"),
           (0x0B00, 0x0B7F, "NotoSansOriya"), (0x0B80, 0x0BFF, "NotoSansTamil"), (0x0C00, 0x0C7F, "NotoSansTelugu"), (0x0C80, 0x0CFF, "NotoSansKannada"),
           (0x0D00, 0x0D7F, "NotoSansMalayalam"), (0x0600, 0x06FF, "NotoSansArabic")]
def is_word(ch): return bool(ch) and (ch.isalnum() or ch == "_")
def bg_and_ink(pix, rect, zoom):
    """paper colour just outside the words + the colour of the letters inside (from the page picture)"""
    W, H = pix.width, pix.height; x0, y0, x1, y1 = [int(v * zoom) for v in (rect.x0, rect.y0, rect.x1, rect.y1)]
    def px(x, y): x = min(W - 1, max(0, x)); y = min(H - 1, max(0, y)); return pix.pixel(x, y)[:3]
    ring = [px(x, y0 - 2) for x in range(x0, x1, 2)] + [px(x, y1 + 2) for x in range(x0, x1, 2)] + [px(x0 - 3, y) for y in range(y0, y1, 2)] + [px(x1 + 3, y) for y in range(y0, y1, 2)]
    med = lambda L: tuple(sorted(v[i] for v in L)[len(L) // 2] for i in range(3)) if L else (255, 255, 255)
    bg = med(ring)
    inside = [px(x, y) for x in range(x0, x1, 1) for y in range(y0, y1, 1)]
    far = sorted(inside, key=lambda p: -sum(abs(p[i] - bg[i]) for i in range(3)))[: max(4, len(inside) // 12)]
    ink = med(far) if far and sum(abs(far[0][i] - bg[i]) for i in range(3)) > 120 else (20, 20, 20)
    return tuple(v / 255 for v in bg), tuple(v / 255 for v in ink)
def span_at(page, rect):
    best = None
    for b in page.get_text("dict")["blocks"]:
        for l in b.get("lines", []):
            for s in l["spans"]:
                r = fitz.Rect(s["bbox"])
                if r.intersects(rect) and (best is None or abs(r.y1 - rect.y1) < abs(best[0].y1 - rect.y1)): best = (r, s)
    return best
total_files = 0
for n, f in enumerate(pdfs, 1):
    base = f["name"][:-4] if f["name"].lower().endswith(".pdf") else f["name"]
    cf = txts.get(base + ".txt") or txts.get("changes.txt") or (list(txts.values())[0] if len(txts) == 1 else None)
    if not cf: print(f"RESULT file {n}: no change list found (add changes.txt)"); continue
    raw = get(cf["id"]); rules = rules_from(raw); pdf_bytes = get(f["id"])
    if not rules and raw.strip():   # a request in plain words -> the private AI (Qwen, from Hugging Face, running on this GitHub machine) writes the exact changes
        try: rules = ai_rules(raw.decode("utf-8-sig", "ignore"), pdf_bytes); print(f"RESULT file {n}: AI planned {len(rules)} change(s)")
        except Exception as e: print(f"RESULT file {n}: AI step failed ({type(e).__name__})"); rules = []
    if not rules: print(f"RESULT file {n}: nothing to change"); continue
    doc = fitz.open(stream=pdf_bytes, filetype="pdf"); changed, pages_hit = 0, set()
    pats = [(re.compile(r"(?<!\w)" + re.escape(o) + r"(?!\w)", re.I), nw) for o, nw in rules]
    def sub_all(t):
        k = 0
        for p, nw in pats: t, c2 = p.subn(lambda m: nw, t); k += c2
        return t, k
    for pg in doc:
        zoom = 3; pix = pg.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False); jobs = []
        area = abs(pg.rect)
        is_scan = any(abs(pg.get_image_bbox(im) & pg.rect) > area * 0.6 for im in pg.get_images(full=True) if not pg.get_image_bbox(im).is_infinite)
        if not is_scan:
            # typed PDF: rewrite each changed piece of text (span) in its exact original place, so nothing else on the line moves
            todo = []
            for b in pg.get_text("dict")["blocks"]:
                for l in b.get("lines", []):
                    if tuple(round(v, 2) for v in l["dir"]) != (1.0, 0.0): continue
                    for s in l["spans"]:
                        t2, k = sub_all(s["text"])
                        if k: todo.append((s, t2, k))
            if not todo: continue
            for s, t2, k in todo:
                r = fitz.Rect(s["bbox"]); bg, _ = bg_and_ink(pix, r, zoom); pg.add_redact_annot(r + (0, -0.3, 0, 0.3), fill=bg)
            pg.apply_redactions(images=fitz.PDF_REDACT_IMAGE_NONE, graphics=fitz.PDF_REDACT_LINE_ART_NONE)
            for s, t2, k in todo:
                r = fitz.Rect(s["bbox"]); size = s["size"]; col = s["color"]; ink = (((col >> 16) & 255) / 255, ((col >> 8) & 255) / 255, (col & 255) / 255)
                bold = "bold" in s["font"].lower() or bool(s["flags"] & 16); ox, oy = s["origin"]
                if t2.strip() and all(ord(ch) < 256 for ch in t2):
                    fn = "hebo" if bold else "helv"; w = fitz.get_text_length(t2, fontname=fn, fontsize=size)
                    if w > r.width * 1.03: size = max(size * 0.72, size * r.width / w)   # longer text shrinks a little to keep its old space
                    pg.insert_text((ox, oy), t2, fontsize=size, fontname=fn, color=ink)
                elif t2.strip():
                    fam = next((nm for lo, hi, nm in SCRIPTS if any(lo <= ord(ch) <= hi for ch in t2)), "NotoSans")
                    css = f"@font-face {{font-family: ind; src: url({fam}-Regular.ttf);}} * {{font-family: ind; font-size: {size}px; color: rgb({int(ink[0]*255)},{int(ink[1]*255)},{int(ink[2]*255)}); margin: 0}}"
                    pg.insert_htmlbox(fitz.Rect(r.x0, r.y0 - size * 0.3, r.x0 + max(r.width * 2, size * len(t2)), r.y1 + size * 0.5), t2, css=css, archive=fitz.Archive(FONTDIR))
                changed += k; pages_hit.add(pg.number)
            continue
        # scanned page (picture + OCR words): erase the picture of the old words, write the new ones
        chars = [(fitz.Rect(ch["bbox"]), ch["c"]) for b in pg.get_text("rawdict")["blocks"] for l in b.get("lines", []) for s in l["spans"] for ch in s["chars"]]
        def neighbour(hit, side):   # the letter touching the match on the left or right (same line), "" if none
            h = hit.height; best, gap = "", h * 0.6
            for r, ch in chars:
                if abs((r.y0 + r.y1) / 2 - (hit.y0 + hit.y1) / 2) > h * 0.5: continue
                d = (hit.x0 - r.x1) if side == "L" else (r.x0 - hit.x1)
                if -h * 0.15 <= d < gap and not (side == "L" and r.x1 > hit.x0 + h * 0.3) and not (side == "R" and r.x0 < hit.x1 - h * 0.3): best, gap = ch, d
            return best
        for old, new in rules:
            for hit in pg.search_for(old):
                # whole words only: the letters right before/after must not be part of a longer word
                if is_word(neighbour(hit, "L")) or is_word(neighbour(hit, "R")): continue
                # exact box of the matched letters only (search boxes can reach into the space or the next letter)
                inside = [r for r, ch in chars if ch.strip() and hit.contains(fitz.Point((r.x0 + r.x1) / 2, (r.y0 + r.y1) / 2))]
                if inside: hit = fitz.Rect(min(r.x0 for r in inside), hit.y0, max(r.x1 for r in inside), hit.y1)
                sp = span_at(pg, hit); size = hit.height * 0.78   # scans: match the height of the letters in the picture
                bold = bool(sp and ("bold" in sp[1]["font"].lower() or sp[1]["flags"] & 16))
                bg, ink = bg_and_ink(pix, hit, zoom)
                if sp:
                    col = sp[1]["color"]; real = ((col >> 16) & 255, (col >> 8) & 255, col & 255)
                    if sum(abs(real[i] / 255 - bg[i]) for i in range(3)) > 0.3: ink = tuple(v / 255 for v in real)   # real text colour (scans keep the picture's colour)
                jobs.append((hit, new, size, bold, bg, ink, sp[0].y1 if sp else hit.y1))
        if not jobs: continue
        PAD = (0.35, -0.6, -0.35, 0.6)   # a little taller than the letters, a hair narrower (never touches the next letter)
        for hit, new, size, bold, bg, ink, base_y in jobs:
            pg.add_redact_annot(hit + PAD, fill=bg)
        pg.apply_redactions(images=fitz.PDF_REDACT_IMAGE_PIXELS, graphics=fitz.PDF_REDACT_LINE_ART_NONE)
        for hit, new, size, bold, bg, ink, base_y in jobs:
            pg.draw_rect(hit + PAD, color=None, fill=bg, overlay=True)   # covers the letters on scanned pictures too
            if not new: continue
            if all(ord(ch) < 256 for ch in new):
                fn = "hebo" if bold else "helv"; w = fitz.get_text_length(new, fontname=fn, fontsize=size)
                if w > hit.width * 1.03: size = max(size * 0.72, size * hit.width / w)   # longer words shrink a little to fit the old space
                pg.insert_text((hit.x0, hit.y1 - hit.height * 0.2), new, fontsize=size, fontname=fn, color=ink)
            else:   # Indian scripts: shaped properly with the matching Noto font
                fam = next((nm for lo, hi, nm in SCRIPTS if any(lo <= ord(ch) <= hi for ch in new)), "NotoSans")
                css = f"@font-face {{font-family: ind; src: url({fam}-Regular.ttf);}} * {{font-family: ind; font-size: {size}px; color: rgb({int(ink[0]*255)},{int(ink[1]*255)},{int(ink[2]*255)}); font-weight: {'bold' if bold else 'normal'}; margin: 0}}"
                pg.insert_htmlbox(fitz.Rect(hit.x0, hit.y0 - size * 0.3, hit.x0 + max(hit.width * 3, size * len(new)), hit.y1 + size * 0.5), new, css=css, archive=fitz.Archive(FONTDIR))
            changed += 1; pages_hit.add(pg.number)
    out = "edited.pdf"; doc.save(out, garbage=3, deflate=True); doc.close()
    dr.files().create(body={"name": f"{base} - edited.pdf", "parents": [done]}, media_body=MediaFileUpload(out, mimetype="application/pdf"), fields="id").execute(); os.remove(out)
    dr.files().update(fileId=f["id"], addParents=orig, removeParents=inbox, fields="id").execute()
    print(f"RESULT file {n}: {changed} change(s) on {len(pages_hit)} page(s)"); total_files += 1
for t in txts.values():   # change lists are used once, then kept with the originals
    dr.files().update(fileId=t["id"], addParents=orig, removeParents=inbox, fields="id").execute()
print(f"RESULT done: {total_files} file(s)")
