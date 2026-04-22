"""Bootstrap script — downloads MaxMind GeoLite2-City.mmdb.

Usage:
  1. Sign up at https://www.maxmind.com/en/geolite2/signup (free)
  2. Generate a license key in your account portal
  3. Add to backend/.env:
        MAXMIND_LICENSE_KEY=your_key_here
  4. Run: `python /app/backend/scripts/download_geolite2.py`

The download is ~60 MB. Re-run weekly (cron) to stay current — MaxMind's
EULA requires that.
"""
from __future__ import annotations

import os
import sys
import tarfile
import tempfile
from pathlib import Path
from urllib.request import urlopen

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

TARGET_DIR = ROOT / "data" / "geolite2"
TARGET_FILE = TARGET_DIR / "GeoLite2-City.mmdb"
URL_TEMPLATE = (
    "https://download.maxmind.com/app/geoip_download?"
    "edition_id=GeoLite2-City&license_key={key}&suffix=tar.gz"
)


def main() -> int:
    key = os.environ.get("MAXMIND_LICENSE_KEY", "").strip()
    if not key:
        print(
            "ERROR: MAXMIND_LICENSE_KEY is not set in backend/.env. "
            "See the header of this script for setup instructions.",
            file=sys.stderr,
        )
        return 2

    TARGET_DIR.mkdir(parents=True, exist_ok=True)
    url = URL_TEMPLATE.format(key=key)
    print(f"Downloading GeoLite2-City to {TARGET_DIR}…")
    with tempfile.NamedTemporaryFile(suffix=".tar.gz", delete=False) as tmp:
        with urlopen(url) as r:
            tmp.write(r.read())
        tmp_path = tmp.name

    with tarfile.open(tmp_path, "r:gz") as tar:
        found = False
        for member in tar.getmembers():
            if member.name.endswith("GeoLite2-City.mmdb"):
                member.name = "GeoLite2-City.mmdb"  # strip leading dir
                tar.extract(member, TARGET_DIR)
                found = True
                break
    Path(tmp_path).unlink(missing_ok=True)

    if not found or not TARGET_FILE.exists():
        print("ERROR: GeoLite2-City.mmdb not found in archive.", file=sys.stderr)
        return 3

    size_mb = TARGET_FILE.stat().st_size / 1024 / 1024
    print(f"OK: wrote {TARGET_FILE} ({size_mb:.1f} MB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
