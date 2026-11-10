# 10 Nov owner: "repositories that could help us for PDF editing ... like OCR, it should run through GitHub".
# Google Drive folder "PDF Tools/1 Inbox": put any PDF (scanned or normal) there.
# This run (GitHub) -> OCRmyPDF (Tesseract: English + Hindi + Telugu + other Indian languages) makes the words real text, then
#   "PDF Tools/2 Done/<name> - OCR.pdf"  (searchable; open it in Page Bench and use Edit text)
#   "PDF Tools/2 Done/<name>.docx"       (Word file made with pdf2docx, to edit in WPS / Word / Google Docs)
# and moves the original to "PDF Tools/3 Originals". Files are never printed or kept on GitHub (this repo is public); logs show file names only.
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
todo = dr.files().list(q=f"'{inbox}' in parents and trashed=false and mimeType='application/pdf'", fields="files(id,name,size)", pageSize=50).execute().get("files", [])
if not todo: print("RESULT inbox empty"); sys.exit(0)
def upload(path, name, mime):
    dr.files().create(body={"name": name, "parents": [done]}, media_body=MediaFileUpload(path, mimetype=mime, resumable=True), fields="id").execute()
for f in todo:
    base = f["name"][:-4] if f["name"].lower().endswith(".pdf") else f["name"]
    src, ocr, docx = "in.pdf", "out.pdf", "out.docx"
    fh = open(src, "wb"); dl = MediaIoBaseDownload(fh, dr.files().get_media(fileId=f["id"])); ok = False
    while not ok: _, ok = dl.next_chunk()
    fh.close()
    # --skip-text: pages that already have real words are kept as they are; only picture pages are read
    r = subprocess.run(["ocrmypdf", "-l", LANGS, "--skip-text", "--rotate-pages", "--deskew", "--output-type", "pdf", "--optimize", "1", src, ocr], capture_output=True, text=True)
    if r.returncode not in (0, 6) or not os.path.exists(ocr):   # 6 = already had text
        print(f"RESULT {f['name']} OCR FAILED code {r.returncode}: {r.stderr.strip()[-200:]}"); ocr = src
    else: print(f"RESULT {f['name']} OCR ok ({LANGS})")
    upload(ocr, f"{base} - OCR.pdf", "application/pdf")
    try:
        from pdf2docx import Converter
        cv = Converter(ocr); cv.convert(docx); cv.close(); upload(docx, f"{base}.docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document")
        print(f"RESULT {f['name']} Word file ok")
    except Exception as e: print(f"RESULT {f['name']} Word file FAILED {str(e)[-120:]}")
    dr.files().update(fileId=f["id"], addParents=orig, removeParents=inbox, fields="id").execute()
    for p in (src, "out.pdf", docx):
        if os.path.exists(p): os.remove(p)
print("RESULT done", len(todo))
