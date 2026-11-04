"""Reads the main text of an article page, when it's free to read."""
import requests
import trafilatura


def fetch(url, cfg):
    """The article's main text (capped in length), or None if we can't get it."""
    polling = cfg["polling"]
    try:
        response = requests.get(url, headers={"User-Agent": polling["user_agent"]},
                                timeout=polling["request_timeout_seconds"])
        response.raise_for_status()
    except requests.RequestException:
        return None
    text = trafilatura.extract(response.text, include_comments=False, include_tables=False)
    if not text or len(text) < 400:  # too short to be the real article (likely a block page)
        return None
    return text[: polling["article_char_cap"]]
