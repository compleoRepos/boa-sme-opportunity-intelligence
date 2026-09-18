#!/usr/bin/env python3
from __future__ import annotations

import sys
import urllib.error
import urllib.request

url = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8080/health"
try:
    with urllib.request.urlopen(url, timeout=3) as response:
        if 200 <= response.status < 300:
            raise SystemExit(0)
except (OSError, urllib.error.URLError):
    pass
raise SystemExit(1)
