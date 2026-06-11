#!/usr/bin/env python3
"""
Einmaliger Google OAuth2 Auth-Flow für Alfred → Google Calendar.

Ausführen:
  cd /Users/timoegersdorfer/alfred
  python3 scripts/gcal_auth.py

Der Flow öffnet einen lokalen Server auf http://localhost:8081.
Du wirst einmalig im Browser nach Google-Berechtigungen gefragt.
Danach wird data/gcal_token.json gespeichert – Alfred läuft danach vollautomatisch.
"""
import json
import sys
from pathlib import Path

# Alfred root in sys.path
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
load_dotenv(ROOT / ".env")

import config

TOKEN_PATH = ROOT / "data" / "gcal_token.json"
SCOPES = ["https://www.googleapis.com/auth/calendar"]
PORT = 8081


def main():
    try:
        from google_auth_oauthlib.flow import Flow
    except ImportError:
        print("❌ Pakete fehlen. Bitte ausführen:")
        print("   pip install google-api-python-client google-auth-oauthlib google-auth-httplib2")
        sys.exit(1)

    client_id     = getattr(config, "GOOGLE_CLIENT_ID", "")
    client_secret = getattr(config, "GOOGLE_CLIENT_SECRET", "")

    if not client_id or not client_secret:
        print("❌ GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET nicht in .env gefunden!")
        sys.exit(1)

    # Web-App-Typ (nicht "installed")
    client_config = {
        "web": {
            "client_id": client_id,
            "client_secret": client_secret,
            "redirect_uris": [f"http://localhost:{PORT}"],
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
        }
    }

    flow = Flow.from_client_config(
        client_config,
        scopes=SCOPES,
        redirect_uri=f"http://localhost:{PORT}",
    )

    auth_url, _ = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent",
    )

    print("🌐 Öffne diesen Link im Browser:\n")
    print(f"  {auth_url}\n")

    # Lokaler Callback-Server
    import urllib.parse
    from http.server import BaseHTTPRequestHandler, HTTPServer

    code_holder = {}

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            parsed = urllib.parse.urlparse(self.path)
            params = urllib.parse.parse_qs(parsed.query)
            if "code" in params:
                code_holder["code"] = params["code"][0]
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b"<h1>Autorisierung erfolgreich! Du kannst diesen Tab schliessen.</h1>")
            else:
                self.send_response(400)
                self.end_headers()
                self.wfile.write(b"Fehler: kein Code erhalten.")

        def log_message(self, *args):
            pass  # Kein HTTP-Log-Spam

    print(f"⏳ Warte auf Callback auf http://localhost:{PORT} ...")
    server = HTTPServer(("localhost", PORT), Handler)
    # Mehrere Requests erlauben (Browser schickt evtl. zuerst favicon etc.)
    while "code" not in code_holder:
        server.handle_request()

    if "code" not in code_holder:
        print("❌ Kein Autorisierungscode erhalten.")
        sys.exit(1)

    flow.fetch_token(code=code_holder["code"])
    creds = flow.credentials

    TOKEN_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(TOKEN_PATH, "w") as f:
        json.dump({
            "token": creds.token,
            "refresh_token": creds.refresh_token,
            "expiry": creds.expiry.isoformat() if creds.expiry else None,
        }, f, indent=2)

    print(f"\n✅ Token gespeichert: {TOKEN_PATH}")
    print("   Alfred kann jetzt Google Kalender-Termine schreiben!")


if __name__ == "__main__":
    main()
