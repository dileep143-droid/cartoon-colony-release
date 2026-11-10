# 10 Nov owner: "something like WPS that scans the image, extracts the text ... run through GitHub ... upload through my phone, edit, download to my phone".
# Phone: put a PDF or a photo (JPG/PNG) in Google Drive "PDF Tools/1 Inbox".
# GitHub (every 5 min or by hand): OCRmyPDF + Tesseract "best" models read every word (English + Indian languages) and add real text to the page
#   -> "PDF Tools/2 Done/<name> - OCR.pdf"  : open it in Page Bench on the phone -> Edit text / Erase (removes the old letters with the background colour)
#   -> "PDF Tools/2 Done/<name> - text.txt" : all the words, to copy
#   -> "PDF Tools/2 Done/<name>.docx"       : Word copy for WPS / Word / Google Docs
# The original moves to "PDF Tools/3 Originals". Files never go into this public repo; logs show file names only.
#   python pdf_ocr.py check   -> writes has_work=true/false for the workflow (fast, before installing OCR)
#   python pdf_ocr.py run
import json, os, subprocess, sys
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload, MediaIoBaseDownload
LANGS = os.environ.get("OCR_LANGS") or "eng+hin+tel"
c = Credentials.from_authorized_user_info(json.loads(os.environ["DRIVE_TOKEN"]))
if not c.valid: c.refresh(Request())
dr = build("drive", "v3", credentials=c, cache_discovery=False)
def folder(nm, parent):
    q = f"name='{nm}' and mimeType='application/vnd.google-apps.folder' and trashed=false and '{parent}' in parents"
    f = dr.files().list(q=q, fields="files(id)").execute().get("files", [])
    return f[0]["id"] if f else dr.files().create(body={"name": nm, "mimeType": "application/vnd.google-apps.folder", "parents": [parent]}, fields="id").execute()["id"]
root = folder("PDF Tools", "root"); inbox, done, orig = folder("1 Inbox", root), folder("2 Done", root), folder("3 Originals", root)
KINDS = {"application/pdf": ".pdf", "image/jpeg": ".jpg", "image/png": ".png", "image/heic": ".heic", "image/webp": ".webp"}
todo = [f for f in dr.files().list(q=f"'{inbox}' in parents and trashed=false", fields="files(id,name,mimeType)", pageSize=50).execute().get("files", []) if f["mimeType"] in KINDS]
if sys.argv[1] == "check":
    open(os.environ["GITHUB_OUTPUT"], "a").write(f"has_work={'true' if todo else 'false'}\n"); print("RESULT inbox:", len(todo), "file(s)"); sys.exit(0)
def upload(path, name, mime):
    dr.files().create(body={"name": name, "parents": [done]}, media_body=MediaFileUpload(path, mimetype=mime, resumable=True), fields="id").execute()
for f in todo:
    ext = KINDS[f["mimeType"]]; base = os.path.splitext(f["name"])[0]; src = "in" + ext
    fh = open(src, "wb"); dl = MediaIoBaseDownload(fh, dr.files().get_media(fileId=f["id"])); ok = False
    while not ok: _, ok = dl.next_chunk()
    fh.close()
    if ext != ".pdf":   # phone photo -> one-page PDF (keeps the photo sharp, fixes its turn)
        from PIL import Image, ImageOps
        if ext == ".heic":
            try: import pillow_heif; pillow_heif.register_heif_opener()
            except Exception: pass
        im = ImageOps.exif_transpose(Image.open(src)).convert("RGB"); im.save("in.pdf", "PDF", resolution=300); src = "in.pdf"
    r = subprocess.run(["ocrmypdf", "-l", LANGS, "--skip-text", "--rotate-pages", "--deskew", "--output-type", "pdf", "--optimize", "1", "--sidecar", "out.txt", src, "out.pdf"], capture_output=True, text=True)
    if r.returncode in (0, 6) and os.path.exists("out.pdf"):
        print(f"RESULT {f['name']} OCR ok ({LANGS})"); upload("out.pdf", f"{base} - OCR.pdf", "application/pdf")
        if os.path.exists("out.txt") and os.path.getsize("out.txt") > 0: upload("out.txt", f"{base} - text.txt", "text/plain")
        try:
            from pdf2docx import Converter
            cv = Converter("out.pdf"); cv.convert("out.docx"); cv.close(); upload("out.docx", f"{base}.docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document")
        except Exception as e: print(f"RESULT {f['name']} Word file skipped {str(e)[-100:]}")
        dr.files().update(fileId=f["id"], addParents=orig, removeParents=inbox, fields="id").execute()
    else:
        print(f"RESULT {f['name']} OCR FAILED code {r.returncode}: {r.stderr.strip()[-200:]} (left in the inbox)")
    for p in ("in.pdf", src, "out.pdf", "out.txt", "out.docx"):
        if os.path.exists(p): os.remove(p)
print("RESULT done", len(todo))
