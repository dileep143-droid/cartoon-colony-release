# Owner 24 Nov: move already-scheduled Shorts from one IST slot today to another time (e.g. tonight 18:30 -> tomorrow 07:00).
#   python shorts_resched.py <lang>   env: FROM_SLOT=18:30  TO=YYYY-MM-DDTHH:MM (IST)  DRY=0/1
# Only PRIVATE videos whose publishAt is exactly today FROM_SLOT IST are moved. Nothing secret is printed.
import datetime, json, os, sys
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
code = sys.argv[1]; DRY = os.environ.get("DRY", "1") != "0"
EXPECT = {"te": "UC2eTiq2nEmcU7udbcivCI5A", "hi": "UC-VXLBB5DbU5A6h3zroABrA", "ta": "UCYMgVtA27zUBsK0Tp2QGtVw",
          "en": "UCQZPvuz9zgLYOjiItiw23Tw", "bn": "UC4WGHUAAhMsP3AETl61TAQw"}
c = Credentials.from_authorized_user_info(json.loads(os.environ["YT_TOKEN"]))
if not c.valid: c.refresh(Request())
yt = build("youtube", "v3", credentials=c, cache_discovery=False)
ch = yt.channels().list(part="contentDetails", mine=True).execute()["items"][0]
if ch["id"] != EXPECT.get(code): print(f"RESULT {code} WRONG CHANNEL"); sys.exit(1)
ist = datetime.timezone(datetime.timedelta(hours=5, minutes=30))
today = datetime.datetime.now(ist).date(); h, m = map(int, os.environ["FROM_SLOT"].split(":"))
frm = datetime.datetime(today.year, today.month, today.day, h, m, tzinfo=ist)
to = datetime.datetime.fromisoformat(os.environ["TO"]).replace(tzinfo=ist)
ids, tok = [], None
while True:
    r = yt.playlistItems().list(part="contentDetails", playlistId=ch["contentDetails"]["relatedPlaylists"]["uploads"], maxResults=50, pageToken=tok).execute()
    ids += [i["contentDetails"]["videoId"] for i in r["items"]]; tok = r.get("nextPageToken")
    if not tok or len(ids) > 300: break
moved = 0
for k in range(0, len(ids), 50):
    for v in yt.videos().list(part="status,snippet", id=",".join(ids[k:k + 50])).execute()["items"]:
        st = v["status"]; pa = st.get("publishAt")
        if st.get("privacyStatus") != "private" or not pa: continue
        t = datetime.datetime.fromisoformat(pa.replace("Z", "+00:00")).astimezone(ist)
        if abs((t - frm).total_seconds()) > 60: continue
        print(f"RESULT {code} {'DRY ' if DRY else ''}MOVE '{v['snippet']['title'][:70]}' {t:%d %b %H:%M} -> {to:%d %b %H:%M} IST", flush=True)
        if not DRY:
            yt.videos().update(part="status", body={"id": v["id"], "status": {"privacyStatus": "private", "publishAt": to.astimezone(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z"),
                                                                              "selfDeclaredMadeForKids": st.get("selfDeclaredMadeForKids", False)}}).execute()
        moved += 1
print(f"RESULT {code} moved {moved}")
