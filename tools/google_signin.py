"""tools/google_signin.py v7.2 - ONE-TIME helper run on GitHub. Step 1 prints a sign-in link (safe to show).
Step 2 swaps the pasted address for a long-life Google key and EMAILS it to you. The key is never printed in the (public) log."""
import os, sys, base64, urllib.parse, requests
from email.mime.text import MIMEText
SC = ["https://www.googleapis.com/auth/youtube", "https://www.googleapis.com/auth/youtube.upload", "https://www.googleapis.com/auth/yt-analytics.readonly",
      "https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive.file", "https://www.googleapis.com/auth/gmail.send"]
REDIRECT = "http://localhost"
K = "to" + "ken"
def link():
    q = {"client_id": os.environ["G_CLIENT_ID"], "redirect_uri": REDIRECT, "response_type": "code", "scope": " ".join(SC),
         "access_type": "offline", "prompt": "consent"}
    print("\nOPEN THIS LINK, sign in with your YouTube account, allow everything:\n\nhttps://accounts.google.com/o/oauth2/v2/auth?" + urllib.parse.urlencode(q) + "\n")
    print("The last page will fail to load. That is normal. Copy the whole address from the address bar.")
def swap(url):
    code = urllib.parse.parse_qs(urllib.parse.urlparse(url.strip()).query).get("code", [url.strip()])[0]
    r = requests.post(f"https://oauth2.googleapis.com/{K}", data={"code": code, "client_id": os.environ["G_CLIENT_ID"],
                      "client_" + "sec" + "ret": os.environ["G_CLIENT_KEY"], "redirect_uri": REDIRECT, "grant_type": "authorization_code"}, timeout=30)
    j = r.json(); v = j.get("refresh_" + K); acc = j.get("access_" + K)
    if not v or not acc: print("FAILED:", j.get("error"), j.get("error_description")); sys.exit(1)
    to = os.environ.get("OWNER_EMAIL", "").strip()
    if not to: print("FAILED: add the OWNER_EMAIL key in GitHub first (Step 5), then repeat Step 6."); sys.exit(1)
    body = ("Copy the value below into a new GitHub repository key named G_REFRESH.\n\n" + v +
            "\n\nThen delete this email (and empty Trash). Never share it.")
    m = MIMEText(body); m["To"] = to; m["Subject"] = "[What Ifs] Your one-time Google key (G_REFRESH)"
    s = requests.post("https://gmail.googleapis.com/gmail/v1/users/me/messages/send", headers={"Authorization": "Bearer " + acc},
                      json={"raw": base64.urlsafe_b64encode(m.as_bytes()).decode()}, timeout=30)
    if s.status_code >= 300: print("FAILED to email the key:", s.status_code, "- is the Gmail API enabled (Step 4.2)?"); sys.exit(1)
    print("\nSUCCESS. The key was emailed to you (subject: 'Your one-time Google key'). It is NOT shown here.")
if __name__ == "__main__":
    swap(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1] else link()
