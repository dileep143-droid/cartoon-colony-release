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
from pdf_core import ai_rules, rules_from, apply_rules
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
    out, changed, npages = apply_rules(pdf_bytes, rules); open("edited.pdf", "wb").write(out); out = "edited.pdf"
    dr.files().create(body={"name": f"{base} - edited.pdf", "parents": [done]}, media_body=MediaFileUpload(out, mimetype="application/pdf"), fields="id").execute(); os.remove(out)
    dr.files().update(fileId=f["id"], addParents=orig, removeParents=inbox, fields="id").execute()
    print(f"RESULT file {n}: {changed} change(s) on {npages} page(s)"); total_files += 1
for t in txts.values():   # change lists are used once, then kept with the originals
    dr.files().update(fileId=t["id"], addParents=orig, removeParents=inbox, fields="id").execute()
print(f"RESULT done: {total_files} file(s)")
