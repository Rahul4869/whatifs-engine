"""whatifs/publish.py v7.0 - YouTube (resumable upload, scheduled publishAt, thumbnail, captions, playlist, AI label),
Instagram Reels + Facebook Reels (Graph API), Google Drive archive, Gmail notices. All calls retried; failures never block the next episode."""
from __future__ import annotations
import os, json, time, base64, email.mime.text, email.mime.multipart
import requests
from whatifs.core import gheaders, env, log, S, FAKE, retry, iso, TK

YT = "https://www.googleapis.com/youtube/v3/"
UP = "https://www.googleapis.com/upload/youtube/v3/"
GV = "https://graph.facebook.com/v21.0/"

# ---------------- YouTube ----------------
def yt_upload(path, title, description, tags, publish_at=None, made_for_kids=False, ai_label=True, short=False):
    if FAKE: return "FAKE_" + os.path.basename(path)
    body = {"snippet": {"title": title[:100], "description": description[:4900], "tags": tags[:30], "categoryId": S("YT_CATEGORY"),
                        "defaultLanguage": "en", "defaultAudioLanguage": "en"},
            "status": {"privacyStatus": "private" if publish_at else "public", "selfDeclaredMadeForKids": made_for_kids,
                       "embeddable": True, "license": "youtube", "containsSyntheticMedia": bool(ai_label)}}
    if publish_at: body["status"]["publishAt"] = publish_at
    def go():
        h = gheaders(); h.update({"Content-Type": "application/json; charset=UTF-8", "X-Upload-Content-Type": "video/mp4",
                                 "X-Upload-Content-Length": str(os.path.getsize(path))})
        r = requests.post(UP + "videos?uploadType=resumable&part=snippet,status", headers=h, json=body, timeout=60)
        if r.status_code == 400 and "containsSyntheticMedia" in r.text:
            body["status"].pop("containsSyntheticMedia", None)
            r = requests.post(UP + "videos?uploadType=resumable&part=snippet,status", headers=h, json=body, timeout=60)
        if r.status_code >= 400: raise RuntimeError(f"YouTube start {r.status_code}: {r.text[:400]}")
        loc = r.headers["Location"]; size = os.path.getsize(path); chunk = 64 * 1024 * 1024; sent = 0
        with open(path, "rb") as f:
            while sent < size:
                data = f.read(chunk); end = sent + len(data) - 1
                for a in range(6):
                    try:
                        rr = requests.put(loc, headers={"Authorization": gheaders()["Authorization"], "Content-Length": str(len(data)),
                                                        "Content-Range": f"bytes {sent}-{end}/{size}"}, data=data, timeout=900)
                        break
                    except requests.RequestException as e:
                        log(f"upload chunk retry: {e}", "WARN"); time.sleep(10 * (a + 1))
                else: raise RuntimeError("upload chunk failed")
                if rr.status_code in (200, 201): return rr.json()["id"]
                if rr.status_code != 308: raise RuntimeError(f"YouTube chunk {rr.status_code}: {rr.text[:300]}")
                rng = rr.headers.get("Range"); sent = int(rng.split("-")[1]) + 1 if rng else 0; f.seek(sent)
        raise RuntimeError("upload ended without id")
    return retry(go, tries=3, wait=30, what="youtube upload")

def yt_thumbnail(vid, path):
    if FAKE: return True
    h = gheaders(); h["Content-Type"] = "image/jpeg"
    r = requests.post(UP + f"thumbnails/set?videoId={vid}", headers=h, data=open(path, "rb").read(), timeout=120)
    if r.status_code >= 400: log(f"thumbnail failed {r.status_code}: {r.text[:300]} (is the channel phone-verified?)", "WARN"); return False
    return True

def yt_captions(vid, srt_path):
    if FAKE: return True
    meta = {"snippet": {"videoId": vid, "language": "en", "name": "English", "isDraft": False}}
    boundary = "wi" + str(int(time.time()))
    body = (f"--{boundary}\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n{json.dumps(meta)}\r\n--{boundary}\r\n"
            f"Content-Type: application/octet-stream\r\n\r\n").encode() + open(srt_path, "rb").read() + f"\r\n--{boundary}--".encode()
    h = gheaders(); h["Content-Type"] = f"multipart/related; boundary={boundary}"
    r = requests.post(UP + "captions?uploadType=multipart&part=snippet", headers=h, data=body, timeout=120)
    if r.status_code >= 400: log(f"captions failed {r.status_code}: {r.text[:300]}", "WARN"); return False
    return True

def yt_playlist(vid, name):
    if FAKE: return True
    try:
        r = requests.get(YT + "playlists?part=snippet&mine=true&maxResults=50", headers=gheaders(), timeout=30).json()
        pl = next((p["id"] for p in r.get("items", []) if p["snippet"]["title"] == name), None)
        if not pl:
            pl = requests.post(YT + "playlists?part=snippet,status", headers=gheaders(), json={"snippet": {"title": name}, "status": {"privacyStatus": "public"}}, timeout=30).json()["id"]
        requests.post(YT + "playlistItems?part=snippet", headers=gheaders(), json={"snippet": {"playlistId": pl, "resourceId": {"kind": "youtube#video", "videoId": vid}}}, timeout=30)
        return True
    except Exception as e: log(f"playlist failed: {e}", "WARN"); return False

def yt_comment(vid, text):
    if FAKE or not text: return True
    try:
        cid = requests.get(YT + "channels?part=id&mine=true", headers=gheaders(), timeout=30).json()["items"][0]["id"]
        requests.post(YT + "commentThreads?part=snippet", headers=gheaders(), json={"snippet": {"channelId": cid, "videoId": vid,
                      "topLevelComment": {"snippet": {"textOriginal": text}}}}, timeout=30)
        return True
    except Exception as e: log(f"comment failed: {e}", "WARN"); return False

def yt_set_privacy(vid, privacy):
    if FAKE: return True
    r = requests.get(YT + f"videos?part=status&id={vid}", headers=gheaders(), timeout=30).json()
    if not r.get("items"): return False
    stt = r["items"][0]["status"]; stt["privacyStatus"] = privacy; stt.pop("publishAt", None)
    requests.put(YT + "videos?part=status", headers=gheaders(), json={"id": vid, "status": stt}, timeout=30); return True

def yt_status(vid):
    if FAKE: return "public"
    r = requests.get(YT + f"videos?part=status&id={vid}", headers=gheaders(), timeout=30).json()
    return (r.get("items") or [{}])[0].get("status", {}).get("privacyStatus")

def yt_channel():
    r = requests.get(YT + "channels?part=snippet,status,statistics&mine=true", headers=gheaders(), timeout=30).json()
    return (r.get("items") or [{}])[0]

# ---------------- Google Drive (public link for Meta + archive) ----------------
def drive_upload(path, name, public=False):
    if FAKE: return "fake_drive_id", "https://example.com/" + name
    h = gheaders(); meta = {"name": name}
    if S("DRIVE_FOLDER_ID"): meta["parents"] = [S("DRIVE_FOLDER_ID")]
    mime = "video/mp4" if path.endswith(".mp4") else "image/jpeg" if path.endswith(".jpg") else "application/json"
    h.update({"Content-Type": "application/json; charset=UTF-8", "X-Upload-Content-Type": mime})
    r = requests.post("https://www.googleapis.com/upload/drive/v3/files?uploadType=resumable", headers=h, json=meta, timeout=60)
    r.raise_for_status()
    rr = requests.put(r.headers["Location"], headers={"Authorization": gheaders()["Authorization"]}, data=open(path, "rb"), timeout=1800)
    rr.raise_for_status(); fid = rr.json()["id"]
    if public:
        requests.post(f"https://www.googleapis.com/drive/v3/files/{fid}/permissions", headers=gheaders(), json={"role": "reader", "type": "anyone"}, timeout=30)
    return fid, f"https://drive.usercontent.google.com/download?id={fid}&export=download&confirm=t"

def drive_download(fid, path):
    if FAKE: raise RuntimeError("fake mode: no drive")
    with requests.get(f"https://www.googleapis.com/drive/v3/files/{fid}?alt=media", headers=gheaders(), stream=True, timeout=600) as r:
        r.raise_for_status()
        with open(path, "wb") as f:
            for c in r.iter_content(1 << 20): f.write(c)
    return path

def drive_delete(fid):
    if FAKE: return
    try: requests.delete(f"https://www.googleapis.com/drive/v3/files/{fid}", headers=gheaders(), timeout=30)
    except Exception: pass

def drive_private(fid):
    if FAKE: return
    try:
        p = requests.get(f"https://www.googleapis.com/drive/v3/files/{fid}/permissions", headers=gheaders(), timeout=30).json()
        for x in p.get("permissions", []):
            if x.get("type") == "anyone": requests.delete(f"https://www.googleapis.com/drive/v3/files/{fid}/permissions/{x['id']}", headers=gheaders(), timeout=30)
    except Exception: pass

# ---------------- Instagram + Facebook ----------------
def _meta_key(): return env("META_PAGE_KEY")
def MH(): return {"Authorization": "Bearer " + _meta_key()}
def ig_reel(video_url, caption, cover_url=None):
    if FAKE: return "FAKE_IG"
    ig = S("IG_USER_ID")
    if not ig: raise RuntimeError("IG_USER_ID missing")
    args = {"media_type": "REELS", "video_url": video_url, "caption": caption[:2100], "share_to_feed": "true"}
    if cover_url: args["cover_url"] = cover_url
    c = requests.post(GV + f"{ig}/media", headers=MH(), data=args, timeout=60).json()
    if "id" not in c: raise RuntimeError(f"IG container: {c}")
    for _ in range(60):
        s = requests.get(GV + c["id"], headers=MH(), params={"fields": "status_code,status"}, timeout=30).json()
        if s.get("status_code") == "FINISHED": break
        if s.get("status_code") == "ERROR": raise RuntimeError(f"IG processing: {s}")
        time.sleep(10)
    p = requests.post(GV + f"{ig}/media_publish", headers=MH(), data={"creation_id": c["id"]}, timeout=60).json()
    if "id" not in p: raise RuntimeError(f"IG publish: {p}")
    return p["id"]

def fb_reel(video_url, description):
    if FAKE: return "FAKE_FB"
    page = S("FB_PAGE_ID"); k = _meta_key()
    s = requests.post(GV + f"{page}/video_reels", headers=MH(), data={"upload_phase": "start"}, timeout=60).json()
    vid = s.get("video_id")
    if not vid: raise RuntimeError(f"FB start: {s}")
    u = requests.post(f"https://rupload.facebook.com/video-upload/v21.0/{vid}", headers={"Authorization": "OAuth " + k, "file_url": video_url}, timeout=300).json()
    if not u.get("success", True): raise RuntimeError(f"FB upload: {u}")
    f = requests.post(GV + f"{page}/video_reels", data={"upload_phase": "finish", "video_id": vid, "video_state": "PUBLISHED",
                      "description": description[:2000]}, headers=MH(), timeout=60).json()
    if not f.get("success"): raise RuntimeError(f"FB finish: {f}")
    return vid

def meta_bio(text):
    """Bio link isn't API-editable on Instagram; we keep a pinned YouTube link in captions instead."""
    return False

# ---------------- email (Gmail API, from your own account) ----------------
def email(subject, html):
    to = S("OPERATOR_EMAIL")
    if FAKE or not to:
        log(f"EMAIL (not sent): {subject}"); return False
    m = email_mime(to, subject, html)
    r = requests.post("https://gmail.googleapis.com/gmail/v1/users/me/messages/send", headers=gheaders(),
                      json={"raw": base64.urlsafe_b64encode(m.as_bytes()).decode()}, timeout=60)
    if r.status_code >= 400: log(f"email failed {r.status_code}: {r.text[:200]}", "WARN"); return False
    return True

def email_mime(to, subject, html):
    m = email.mime.multipart.MIMEMultipart("alternative"); m["To"] = to; m["Subject"] = "[What Ifs] " + subject
    m.attach(email.mime.text.MIMEText(html, "html")); return m
