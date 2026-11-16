"""Family Movie Night proxy.

The movie page is served by this service so the public link lives on a normal
host (works in any browser). The data still lives in Tiram's Google Sheet;
this module talks to the Apps Script JSON API server-side, which avoids the
browser multi-Google-account failure that breaks script.google.com pages
when opened directly.
"""
import json, os, urllib.parse, urllib.request, urllib.error

EXEC_URL = os.environ.get(
    "MOVIENIGHT_EXEC_URL",
    "https://script.google.com/macros/s/AKfycbzr_w09tL3HeFdDMg2f0wWP9V25EGDkFQgmxvUFykgKwwgtvn-exEGLZj58E6DB7yJSoA/exec",
)
API_KEY = os.environ.get("MOVIENIGHT_API_KEY", "fmnight-7f3ka9")
TIMEOUT = 25


def _call(payload):
    """Call the Apps Script API with a GET (Apps Script POST redirects hang
    in common HTTP clients; GET actions are reliable) and return its reply."""
    params = dict(payload or {})
    for key, value in list(params.items()):
        if isinstance(value, bool):
            params[key] = "true" if value else "false"
    params["api"] = "1"
    params["k"] = API_KEY
    url = EXEC_URL + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, method="GET")
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        return json.loads(resp.read().decode("utf-8"))


def list_movies():
    return _call({"action": "list"})


def add_movie(title):
    return _call({"action": "add", "title": title})


def vote_movie(row):
    return _call({"action": "vote", "row": row})


def set_watched(row, watched):
    return _call({"action": "watched", "row": row, "watched": bool(watched)})


def delete_movie(row):
    return _call({"action": "delete", "row": row})
