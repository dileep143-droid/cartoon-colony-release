# 10 Nov owner: "I want to control it through my phone" -> a private Telegram bot.
# Send the bot a PDF with a caption like "change the date to today and Ravi to Suresh" (or lines "old => new").
# GitHub (every 5 min) picks it up, the private Qwen AI (Hugging Face, running on GitHub) plans the changes, pdf_core edits, the bot replies with the edited PDF.
# Only the owner can use it: the first chat that writes to the bot becomes the owner (kept in Google Drive "PDF Tools/bot_state.json"); everyone else is ignored.
# Nothing from the document or the request is printed in this public log - only counts.
#   python tg_pdf_bot.py check | run          (needs the TG_BOT_TOKEN secret; without it the bot just stays off)
import io, json, os, subprocess, sys, urllib.parse, urllib.request
TOKEN = os.environ.get("TG_BOT_TOKEN", "").strip(); API = f"https://api.telegram.org/bot{TOKEN}"
def out(k, v): open(os.environ["GITHUB_OUTPUT"], "a").write(f"{k}={v}\n") if os.environ.get("GITHUB_OUTPUT") else None
def tg(method, **params):
    data = urllib.parse.urlencode({k: (json.dumps(v) if isinstance(v, (dict, list)) else v) for k, v in params.items()}).encode()
    with urllib.request.urlopen(urllib.request.Request(f"{API}/{method}", data=data), timeout=60) as r: return json.loads(r.read())["result"]
if not TOKEN: print("RESULT bot not set up yet (no TG_BOT_TOKEN secret)"); out("has_work", "false"); sys.exit(0)
ups = tg("getUpdates", timeout=0, allowed_updates=["message"])
if sys.argv[1] == "check":
    out("has_work", "true" if ups else "false"); print(f"RESULT {len(ups)} new message(s)"); sys.exit(0)
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload, MediaIoBaseDownload
c = Credentials.from_authorized_user_info(json.loads(os.environ["DRIVE_TOKEN"]))
if not c.valid: c.refresh(Request())
dr = build("drive", "v3", credentials=c, cache_discovery=False)
def folder(nm, parent):
    q = f"name='{nm}' and mimeType='application/vnd.google-apps.folder' and trashed=false and '{parent}' in parents"
    f = dr.files().list(q=q, fields="files(id)").execute().get("files", [])
    return f[0]["id"] if f else dr.files().create(body={"name": nm, "mimeType": "application/vnd.google-apps.folder", "parents": [parent]}, fields="id").execute()["id"]
root = folder("PDF Tools", "root")
sf = dr.files().list(q=f"name='bot_state.json' and '{root}' in parents and trashed=false", fields="files(id)").execute().get("files", [])
state = {}
if sf:
    b = io.BytesIO(); dl = MediaIoBaseDownload(b, dr.files().get_media(fileId=sf[0]["id"])); ok = False
    while not ok: _, ok = dl.next_chunk()
    state = json.loads(b.getvalue() or b"{}")
def save_state():
    media = MediaIoBaseUpload(io.BytesIO(json.dumps(state).encode()), mimetype="application/json")
    if sf: dr.files().update(fileId=sf[0]["id"], media_body=media).execute()
    else: dr.files().create(body={"name": "bot_state.json", "parents": [root]}, media_body=media, fields="id").execute()
def say(chat, text): tg("sendMessage", chat_id=chat, text=text)
def download(file_id):
    p = tg("getFile", file_id=file_id)["file_path"]
    with urllib.request.urlopen(f"https://api.telegram.org/file/bot{TOKEN}/{p}", timeout=120) as r: return r.read()
def send_pdf(chat, data, name, caption):
    bnd = "----pdfbot"; body = io.BytesIO()
    for k, v in (("chat_id", str(chat)), ("caption", caption)):
        body.write(f"--{bnd}\r\nContent-Disposition: form-data; name=\"{k}\"\r\n\r\n{v}\r\n".encode())
    body.write(f"--{bnd}\r\nContent-Disposition: form-data; name=\"document\"; filename=\"{name}\"\r\nContent-Type: application/pdf\r\n\r\n".encode() + data + f"\r\n--{bnd}--\r\n".encode())
    urllib.request.urlopen(urllib.request.Request(f"{API}/sendDocument", data=body.getvalue(), headers={"Content-Type": f"multipart/form-data; boundary={bnd}"}), timeout=120).read()
HELP = ("Send me a PDF with a caption saying what to change, for example:\n"
        "change the date to today and Ravi Kumar to Suresh Reddy everywhere\n\n"
        "or exact lines like:\n10 November => 12 November\n\nI reply with the edited PDF in a few minutes. Only you can use this bot.")
def process(chat, file_id, name, request):
    import pymupdf as fitz
    from pdf_core import ai_rules, rules_from, apply_rules
    say(chat, "Got it, working on it...")
    pdf = download(file_id)
    if sum(len(p.get_text().strip()) for p in fitz.open(stream=pdf, filetype="pdf")) < 20:   # a scan: read the words first (OCR)
        say(chat, "This looks like a scan. Reading the words first (a few extra minutes)...")
        subprocess.run("sudo apt-get install -y -qq ocrmypdf tesseract-ocr-hin tesseract-ocr-tel > /dev/null 2>&1", shell=True)
        open("scan.pdf", "wb").write(pdf)
        r = subprocess.run(["ocrmypdf", "-l", "eng+hin+tel", "--skip-text", "--deskew", "scan.pdf", "scan_ocr.pdf"], capture_output=True)
        if r.returncode in (0, 6) and os.path.exists("scan_ocr.pdf"): pdf = open("scan_ocr.pdf", "rb").read()
    rules = rules_from(request)
    if not rules:
        try: rules = ai_rules(request, pdf)
        except Exception as e: print("RESULT AI step failed", type(e).__name__); rules = []
    if not rules: say(chat, "I couldn't find those words in the PDF. Try writing the exact old words, like:\nold words => new words"); return
    data, n, pages = apply_rules(pdf, rules)
    base = name[:-4] if name.lower().endswith(".pdf") else name
    send_pdf(chat, data, f"{base} - edited.pdf", f"Done: {n} change(s) on {pages} page(s). Please check it before using it.")
    print(f"RESULT edited: {n} change(s) on {pages} page(s)")
last = 0
for u in ups:
    last = max(last, u["update_id"]); m = u.get("message") or {}; chat = m.get("chat", {}).get("id")
    if not chat: continue
    if not state.get("owner"):
        state["owner"] = chat; save_state(); say(chat, "Hi! This bot is now yours - it will only answer you.\n\n" + HELP); print("RESULT owner set")
        if not m.get("document"): continue
    if chat != state["owner"]: print("RESULT ignored a stranger"); continue
    doc = m.get("document"); text = (m.get("caption") or m.get("text") or "").strip()
    try:
        if doc and (doc.get("mime_type") == "application/pdf" or doc.get("file_name", "").lower().endswith(".pdf")):
            if doc.get("file_size", 0) > 19_000_000: say(chat, "That PDF is over 19 MB - Telegram bots can't download it. Please send a smaller file."); continue
            if text: process(chat, doc["file_id"], doc.get("file_name", "document.pdf"), text)
            else: state["pending"] = [doc["file_id"], doc.get("file_name", "document.pdf")]; save_state(); say(chat, "Got the PDF. Now tell me what to change.")
        elif text and text.lower() not in ("/start", "/help", "hi", "hello") and state.get("pending"):
            fid, nm = state.pop("pending"); save_state(); process(chat, fid, nm, text)
        else: say(chat, HELP)
    except Exception as e:
        print("RESULT failed", type(e).__name__); say(chat, "Sorry, something went wrong with that one. Please try again.")
if last: tg("getUpdates", offset=last + 1, timeout=0)   # mark these messages as handled
print(f"RESULT handled {len(ups)} message(s)")
