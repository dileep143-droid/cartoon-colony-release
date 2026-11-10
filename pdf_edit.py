# 10 Nov owner: "blind" PDF editing on GitHub - nobody (not Claude, not this public log) sees the document.
# Google Drive "PDF Tools/Edit Inbox":
#   your PDF(s) + a text file "changes.txt" (one change per line:  old words => new words)
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
    rules = rules_from(get(cf["id"]))
    doc = fitz.open(stream=get(f["id"]), filetype="pdf"); changed, pages_hit = 0, set()
    for pg in doc:
        zoom = 3; pix = pg.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False); jobs = []
        for old, new in rules:
            for hit in pg.search_for(old):
                # whole words only: the letters right before/after must not be part of a longer word
                h = hit.height; left = pg.get_textbox(fitz.Rect(hit.x0 - h * 0.6, hit.y0, hit.x0 - 0.5, hit.y1)).strip()[-1:]
                right = pg.get_textbox(fitz.Rect(hit.x1 + 0.5, hit.y0, hit.x1 + h * 0.6, hit.y1)).strip()[:1]
                if is_word(left) or is_word(right): continue
                sp = span_at(pg, hit); size = sp[1]["size"] if sp else h * 0.8; bold = bool(sp and ("bold" in sp[1]["font"].lower() or sp[1]["flags"] & 16))
                bg, ink = bg_and_ink(pix, hit, zoom)
                if sp:
                    col = sp[1]["color"]; real = ((col >> 16) & 255, (col >> 8) & 255, col & 255)
                    if sum(abs(real[i] / 255 - bg[i]) for i in range(3)) > 0.3: ink = tuple(v / 255 for v in real)   # real text colour (scans keep the picture's colour)
                jobs.append((hit, new, size, bold, bg, ink, sp[0].y1 if sp else hit.y1))
        if not jobs: continue
        for hit, new, size, bold, bg, ink, base_y in jobs:
            pg.add_redact_annot(hit + (-0.5, -0.5, 0.5, 0.5), fill=bg)
        pg.apply_redactions(images=fitz.PDF_REDACT_IMAGE_PIXELS, graphics=fitz.PDF_REDACT_LINE_ART_NONE)
        for hit, new, size, bold, bg, ink, base_y in jobs:
            pg.draw_rect(hit + (-0.5, -0.5, 0.5, 0.5), color=None, fill=bg, overlay=True)   # covers the letters on scanned pictures too
            if not new: continue
            if all(ord(ch) < 256 for ch in new):
                pg.insert_text((hit.x0, hit.y1 - size * 0.22), new, fontsize=size, fontname="hebo" if bold else "helv", color=ink)
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
