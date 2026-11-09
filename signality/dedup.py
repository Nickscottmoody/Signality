"""Free duplicate detection: clean links and compare headlines.

Two kinds of duplicates:
1. Exact repeats - the same article seen again on the next check. Caught by
   its cleaned link or the feed's own id, and skipped.
2. Same story, different outlet - Reuters and Bloomberg both covering one
   event. These are NOT thrown away: they're grouped under one story, because
   independent coverage is evidence for the claims inside it (Stage 2b).

This file catches headlines that are nearly identical. "Same event, very
different wording" needs real language understanding, which Claude Haiku adds
in Stage 2a.
"""
import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

# Link parameters that only track clicks; removing them lets the same article
# from two links be recognized as one.
TRACKING_PARAM = re.compile(
    r"^(utm_\w+|fbclid|gclid|mc_cid|mc_eid|cmpid|smid|ref|sref|taid|mod)$", re.I
)

# Common words that say nothing about what a headline is about.
STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "for", "from", "has", "have",
    "how", "in", "into", "is", "it", "its", "new", "of", "on", "or", "over",
    "says", "say", "said", "that", "the", "their", "this", "to", "up", "was",
    "what", "when", "why", "will", "with", "after", "amid", "about", "more",
    "than", "you", "your", "can", "could", "may", "now", "just", "here", "who",
}

# Google News adds the outlet to the end of every headline: "... - Reuters".
OUTLET_SUFFIX = re.compile(r"\s+[-–—|]\s+[^-–—|]{1,40}$")


def clean_url(url):
    """Lowercase the address, drop tracking codes and '#section' parts."""
    parts = urlsplit(url.strip())
    query = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True)
             if not TRACKING_PARAM.match(k)]
    path = parts.path.rstrip("/") or "/"
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), path,
                       urlencode(query), ""))


def strip_outlet_suffix(title):
    """'OpenAI raises $40B - Reuters' -> 'OpenAI raises $40B'."""
    return OUTLET_SUFFIX.sub("", title).strip()


def title_words(title):
    """The meaningful words in a headline, lowercase, as a set."""
    words = re.findall(r"[a-z0-9$%.\-]+", title.lower())
    words = {w.strip(".-") for w in words}
    return {w for w in words if w and w not in STOPWORDS}


def similarity(words_a, words_b):
    """How alike two headlines are, from 0 (nothing shared) to 1 (identical).

    Measured as shared words / total distinct words (the Jaccard index).
    """
    if not words_a or not words_b:
        return 0.0
    return len(words_a & words_b) / len(words_a | words_b)


# Words in so many AI headlines that sharing them says nothing about being the same story.
TOO_COMMON = {"ai", "a.i", "artificial", "intelligence", "tech", "data", "model", "models", "company",
              "companies", "billion", "million", "new", "deal", "us", "u.s"}


def key_words(title):
    """The distinctive words of a headline (e.g. {'nvidia', 'huang', 'probe'})."""
    return title_words(title) - TOO_COMMON


def related(words_a, words_b):
    """True if two headlines share at least two distinctive words (same saga, maybe different angle)."""
    return len(words_a & words_b) >= 2
