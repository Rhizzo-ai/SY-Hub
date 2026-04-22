"""MaxMind GeoLite2 wrapper.

Ship without the `.mmdb` file — every lookup gracefully returns `None` so
callers don't need to special-case missing data. To enable real lookups:

  1. Create a free MaxMind account: https://www.maxmind.com/en/geolite2/signup
  2. Generate a license key.
  3. Run: `python /app/backend/scripts/download_geolite2.py`
     (needs MAXMIND_LICENSE_KEY in backend/.env)
  4. That'll drop GeoLite2-City.mmdb into /app/backend/data/geolite2/
     which this module auto-detects on next request.

Note: MaxMind's EULA requires you keep the file up to date — the bootstrap
script can be put on a weekly cron. For Phase 1 dev, the fallback `None`
path is fine; login history just shows country=NULL.
"""
from __future__ import annotations

import ipaddress
import logging
import os
from dataclasses import dataclass
from decimal import Decimal
from functools import lru_cache
from pathlib import Path
from typing import Optional

log = logging.getLogger("syhomes.geo")

DEFAULT_MMDB_PATH = Path("/app/backend/data/geolite2/GeoLite2-City.mmdb")


@dataclass
class GeoLocation:
    country: Optional[str]
    city: Optional[str]
    latitude: Optional[Decimal]
    longitude: Optional[Decimal]


@lru_cache(maxsize=1)
def _reader():
    path = Path(os.environ.get("GEOLITE2_MMDB_PATH", str(DEFAULT_MMDB_PATH)))
    if not path.exists():
        log.info("GeoLite2 mmdb not found at %s — geolocation disabled", path)
        return None
    try:
        import geoip2.database  # lazy
        return geoip2.database.Reader(str(path))
    except Exception as e:  # pragma: no cover
        log.warning("Failed to open GeoLite2 mmdb at %s: %s", path, e)
        return None


def _is_private(ip: str) -> bool:
    try:
        a = ipaddress.ip_address(ip)
        return a.is_private or a.is_loopback or a.is_link_local or a.is_multicast
    except ValueError:
        return True


def geolocate(ip: str) -> GeoLocation:
    """Return geo info for `ip`. Private/unresolvable IPs → Local/None."""
    if not ip:
        return GeoLocation(None, None, None, None)
    if _is_private(ip):
        return GeoLocation(country="Local", city=None, latitude=None, longitude=None)

    r = _reader()
    if r is None:
        return GeoLocation(None, None, None, None)

    try:
        resp = r.city(ip)
    except Exception:
        return GeoLocation(None, None, None, None)

    country = (resp.country.name or "").strip() or None
    city = (resp.city.name or "").strip() or None
    lat = Decimal(str(resp.location.latitude)) if resp.location.latitude else None
    lon = Decimal(str(resp.location.longitude)) if resp.location.longitude else None
    return GeoLocation(country, city, lat, lon)
