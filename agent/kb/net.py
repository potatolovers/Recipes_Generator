"""HTTP GET with a polite pause, retries and an identifying User-Agent (Wikimedia requires one)."""

import json
import time
import urllib.error
import urllib.parse
import urllib.request

USER_AGENT = ("ShiweiRecipeKB/0.1 (personal learning project; "
              "https://github.com/potatolovers/Recipes_Generator)")
PAUSE_SECONDS = 0.3


def get_bytes(url: str, params: dict | None = None, retries: int = 3) -> bytes:
    if params:
        url = f"{url}?{urllib.parse.urlencode(params)}"
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                body = response.read()
            time.sleep(PAUSE_SECONDS)
            return body
        except urllib.error.HTTPError as exc:
            if (exc.code < 500 and exc.code != 429) or attempt == retries - 1:
                raise
        except (urllib.error.URLError, TimeoutError):
            if attempt == retries - 1:
                raise
        time.sleep(2 * 2 ** attempt)
    raise AssertionError("unreachable")


def get_text(url: str, params: dict | None = None) -> str:
    return get_bytes(url, params).decode("utf-8")


def get_json(url: str, params: dict | None = None):
    return json.loads(get_bytes(url, params))
