"""Helper — seed test users, log in as test-admin with MFA auto-enrol, emit cookies JSON."""
import os, sys, json, subprocess, pyotp, requests

BASE = os.environ.get("REACT_APP_BACKEND_URL", "https://production-contract-1.preview.emergentagent.com").rstrip("/")
EMAIL = "test-admin@example.test"
PW = "TestUser-Dev-2026!"

def seed():
    subprocess.run([sys.executable, "scripts/seed_test_users.py"], cwd="/app/backend", check=True, capture_output=True)

def login_session():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    r = s.post(f"{BASE}/api/auth/login", json={"email": EMAIL, "password": PW, "remember_me": False})
    r.raise_for_status()
    d = r.json()
    if d.get("mfa_enrollment_required"):
        start = s.post(f"{BASE}/api/auth/mfa/enroll/start"); start.raise_for_status()
        secret = start.json()["secret"]
        c = s.post(f"{BASE}/api/auth/mfa/enroll/confirm",
                   json={"secret": secret, "code": pyotp.TOTP(secret).now()})
        c.raise_for_status()
    return s

def cookies_for_playwright(s):
    # Playwright wants: name, value, domain, path
    from urllib.parse import urlparse
    host = urlparse(BASE).hostname
    out = []
    for c in s.cookies:
        out.append({"name": c.name, "value": c.value,
                    "domain": c.domain or host, "path": c.path or "/",
                    "secure": True, "sameSite": "Lax"})
    return out

if __name__ == "__main__":
    seed()
    s = login_session()
    print(json.dumps(cookies_for_playwright(s)))
