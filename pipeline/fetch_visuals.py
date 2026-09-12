#!/usr/bin/env python3
"""Fetch real visuals for a video, one asset per script beat (see generate_script.py) —
actual filmed stock footage where a query matches something filmable, real archival
images (Wikimedia Commons / Wikidata) for things only paintings/artifacts/portraits can
show, otherwise a plain gradient as a last resort. Free, no paid tier needed.

Usage: fetch_visuals.py <out_dir> "<query 1>" "<query 2>" ...  (CLI form: plain scene
queries, for manual testing — the real caller is run_pipeline.py, which passes full beat
dicts with entity_type so a named person gets their actual portrait, see fetch_all()).

One asset is fetched per beat, saved as <out_dir>/img_00.<ext>, img_01.<ext>, ... where
<ext> is .mp4 for real video or .jpg for a still image — render.py tells them apart by
extension. fetch_all() returns per-asset metadata (source, entity_type, detected face
center) alongside each path, not just a bare path list, so render.py can frame a
Ken Burns pan/zoom around an actual detected face instead of blind-cropping to center.

Source order:
- entity_type == "person": Wikidata portrait (the P18 image claim on the Wikidata item
  matching the query) -> Wikimedia Commons keyword search -> Europeana -> Flickr
  Commons -> Google Custom Search (license-filtered) -> gradient placeholder.
  Deliberately NO Pexels/NASA fallback here — Pexels is generic modern stock
  photography of anonymous models, and NASA's collection has no bearing on a person
  portrait; using either to stand in for a specific named historical figure is exactly
  the "random dude" problem this beat-level sourcing exists to avoid. An honest
  abstract placeholder is less misleading than the wrong face.
- everything else: Internet Archive (public-domain film, real footage preferred over
  generic stock) -> Pexels Video (needs PEXELS_API_KEY) -> Wikimedia Commons image ->
  NASA Images -> Europeana -> Flickr Commons -> Google Custom Search -> Pexels Photo
  (needs PEXELS_API_KEY) -> gradient placeholder. Every source past Commons is real,
  license-checked, and gracefully skipped (not a hard failure) when its own API key
  isn't configured or it returns nothing relevant — see each source's own function for
  its specific license-verification method (per-item rights metadata for Europeana/
  Google CSE, agency-wide public-domain default for NASA, "no known restrictions" for
  Flickr Commons specifically, not Flickr generally).
"""
import math
import os
import re
import subprocess
import sys
import time
from pathlib import Path

import cv2
import numpy as np
import requests
from PIL import Image

import illustrate

COMMONS_API = "https://commons.wikimedia.org/w/api.php"
WIKIDATA_API = "https://www.wikidata.org/w/api.php"
PEXELS_VIDEO_API = "https://api.pexels.com/videos/search"
PEXELS_PHOTO_API = "https://api.pexels.com/v1/search"
ARCHIVE_ORG_SEARCH_API = "https://archive.org/advancedsearch.php"
ARCHIVE_ORG_METADATA_API = "https://archive.org/metadata"
HEADERS = {"User-Agent": "history-shorts-local-project/0.1 (personal hobby project)"}
PEXELS_API_KEY = os.environ.get("PEXELS_API_KEY", "")

MIN_IMAGE_WIDTH = 500
MIN_VIDEO_WIDTH = 480
ALLOWED_IMAGE_MIME = {"image/jpeg", "image/png"}


def _commons_imageinfo(params: dict) -> str | None:
    resp = requests.get(COMMONS_API, headers=HEADERS, params=params, timeout=20)
    resp.raise_for_status()
    pages = resp.json().get("query", {}).get("pages", {})
    for page in sorted(pages.values(), key=lambda p: p.get("index", 999)):
        info = (page.get("imageinfo") or [None])[0]
        if not info or info.get("mime") not in ALLOWED_IMAGE_MIME:
            continue
        if info.get("width", 0) < MIN_IMAGE_WIDTH:
            continue
        return info["url"]
    return None


def _commons_search(query: str) -> str | None:
    return _commons_imageinfo({
        "action": "query",
        "generator": "search",
        "gsrnamespace": 6,
        "gsrsearch": query,
        "gsrlimit": 10,
        "prop": "imageinfo",
        "iiprop": "url|size|mime",
        "format": "json",
    })


# Both Wikidata's wbsearchentities (an entity-name match, not full-text search) and
# Commons' own keyword search return nothing — or the wrong thing — for a query like
# "Roman Emperor Aurelian portrait", even though "Aurelian" alone matches immediately on
# both. The LLM is deliberately told to write specific, descriptive queries (that's what
# makes the SAME query work well against Pexels/Commons for non-person beats), so rather
# than change the prompt, strip both ends down to what's most likely the bare name and
# try progressively narrower candidates — used by both the Wikidata lookup and the
# Commons fallback below, since both have this problem.
_LEADING_TITLES = {
    "roman", "greek", "egyptian", "emperor", "empress", "king", "queen", "pharaoh",
    "general", "prince", "princess", "president", "sir", "dr", "saint", "st", "pope",
    "duke", "duchess", "tsar", "tsarina", "sultan", "lord", "lady", "captain", "admiral",
    "colonel", "chief", "chancellor", "senator",
}
_TRAILING_DESCRIPTORS = {
    "portrait", "photo", "photograph", "statue", "bust", "painting", "engraving",
    "illustration", "drawing", "sketch", "picture", "image", "likeness", "throne",
    "coin", "relief", "mosaic", "fresco", "seal", "monument", "crown", "tomb", "mask",
    "effigy", "medallion", "figurine", "sculpture", "depiction", "artwork", "mural",
}


def _strip_leading_titles(query: str) -> str:
    words = query.split()
    while len(words) > 1 and words[0].lower().strip(".,") in _LEADING_TITLES:
        words = words[1:]
    return " ".join(words)


def _strip_trailing_descriptor(query: str) -> str:
    words = query.split()
    while len(words) > 1 and words[-1].lower().strip(".,") in _TRAILING_DESCRIPTORS:
        words = words[:-1]
    return " ".join(words)


def _name_candidates(query: str) -> list[str]:
    """Progressively narrower candidates, most-specific first, deduplicated."""
    stripped = _strip_trailing_descriptor(_strip_leading_titles(query))
    candidates = [query, _strip_leading_titles(query), _strip_trailing_descriptor(query), stripped]
    return list(dict.fromkeys(c for c in candidates if c))


def _wikidata_qids(name: str, limit: int = 4) -> list[str]:
    """Several candidate items, not just the top hit — wbsearchentities' first result is
    sometimes a sparse/near-empty duplicate or homonym item with no P18 claim at all,
    while a well-documented item for the same name ranks lower."""
    resp = requests.get(
        WIKIDATA_API,
        headers=HEADERS,
        params={"action": "wbsearchentities", "search": name, "language": "en", "type": "item", "limit": limit, "format": "json"},
        timeout=20,
    )
    resp.raise_for_status()
    return [h["id"] for h in (resp.json().get("search") or [])]


def _wikidata_p18_image(qid: str) -> str | None:
    claims = requests.get(
        WIKIDATA_API,
        headers=HEADERS,
        params={"action": "wbgetclaims", "entity": qid, "property": "P18", "format": "json"},
        timeout=20,
    )
    claims.raise_for_status()
    p18 = (claims.json().get("claims") or {}).get("P18")
    if not p18:
        return None
    try:
        filename = p18[0]["mainsnak"]["datavalue"]["value"]
    except (KeyError, IndexError, TypeError):
        return None

    return _commons_imageinfo({
        "action": "query",
        "titles": f"File:{filename}",
        "prop": "imageinfo",
        "iiprop": "url|size|mime",
        "format": "json",
    })


def _wikidata_portrait(name: str) -> str | None:
    """Tries several name candidates (see _name_candidates), and for each, several
    Wikidata items (see _wikidata_qids) — the first item with an actual usable P18
    image wins. None only once every candidate item is exhausted; falls through to the
    Commons keyword search from there. Paced (a beat that needs this many attempts is
    rare) since this can otherwise fire a burst of Wikidata requests fast enough to get
    429'd mid-search."""
    first = True
    for candidate in _name_candidates(name):
        if not first:
            time.sleep(0.3)
        first = False
        try:
            qids = _wikidata_qids(candidate)
        except requests.exceptions.RequestException:
            continue
        for qid in qids:
            time.sleep(0.3)
            try:
                image = _wikidata_p18_image(qid)
            except requests.exceptions.RequestException:
                continue
            if image:
                return image
    return None


_ARCHIVE_STOPWORDS = frozenset({
    "a", "an", "the", "of", "in", "at", "on", "and", "to", "with", "his", "her", "their",
    "its", "for", "from", "by", "as", "is", "was", "were", "are", "this", "that",
})


def _archive_significant_words(text: str) -> set[str]:
    """Same bag-of-significant-words approach already used for transition-continuity
    matching (render.py's _subject_key) — reused here for a different purpose:
    confirming an Internet Archive search RESULT is actually about the query, not just
    a keyword collision."""
    words = re.findall(r"[a-z0-9]+", text.lower())
    return {w for w in words if w not in _ARCHIVE_STOPWORDS and len(w) > 2}


def _title_relevant(query: str, title: str) -> bool:
    """Shared relevance gate — originally built for Internet Archive (see
    _archive_org_search's own docstring for the real "ancient Rome" / "Advance on
    Rome, 1944" false-positive story behind the exact threshold below), now reused by
    every keyword-search-based source added since (NASA, Europeana, Flickr Commons,
    Google Custom Search) since they all have the identical failure mode: a search
    API's own relevance ranking is not a guarantee the top result is actually on
    topic. MORE than half the query's own significant words must appear in the
    candidate's title — deliberately strict (>) rather than >=, so a single shared
    word in a 2-word query can't pass alone."""
    query_words = _archive_significant_words(query)
    if not query_words:
        return False
    title_words = _archive_significant_words(title)
    overlap = query_words & title_words
    return len(overlap) / len(query_words) > 0.5


def _archive_org_search(query: str) -> str | None:
    """Internet Archive's public-domain film collections (Prelinger and others) — a
    real, legally clean source of historical footage (see Claude outputs/OPEN_ISSUES.md
    #61's sibling item for why this was added over scraping YouTube: even a CC-licensed
    YouTube video generally can't be downloaded without violating YouTube's own ToS,
    separate from the footage's own license). Strong for 20th-century subject matter
    (WWII newsreels, etc. — real film exists); essentially empty for anything before
    the film era, where a keyword search can still return a false-positive match on a
    shared word (e.g. "Advance on Rome", a 1944 newsreel, matching a query for "ancient
    Rome" on the word "Rome" alone) — `mediatype:movies` and a real public-domain
    license filter handle legality, but NOT relevance, hence the word-overlap check
    below on top of the API's own relevance ranking.

    Returns an item identifier, or None if nothing both license-clean AND genuinely
    on-topic was found — callers fall through to the existing Pexels/Commons waterfall
    exactly as if this source didn't exist, same graceful-degradation pattern as
    everywhere else in this module."""
    resp = requests.get(
        ARCHIVE_ORG_SEARCH_API,
        headers=HEADERS,
        params={
            "q": f"{query} AND mediatype:(movies) AND licenseurl:(*publicdomain*)",
            "fl[]": ["identifier", "title"],
            "rows": 5,
            "output": "json",
        },
        timeout=20,
    )
    resp.raise_for_status()
    docs = resp.json().get("response", {}).get("docs", [])
    for doc in docs:
        if _title_relevant(query, doc.get("title", "")):
            return doc.get("identifier")
    return None


def _archive_org_video_url(identifier: str) -> str | None:
    """Prefers a real, reasonably-sized derivative (the "_512kb.mp4" transcode Internet
    Archive generates for most film-collection items) over the original — often a much
    larger, higher-bitrate master not worth the download/decode cost for a few seconds
    of footage in a short-form video. Falls back to any other real .mp4 derivative if
    the 512kb one isn't present for this particular item."""
    resp = requests.get(f"{ARCHIVE_ORG_METADATA_API}/{identifier}", headers=HEADERS, timeout=20)
    resp.raise_for_status()
    files = resp.json().get("files", [])
    mp4_files = [f for f in files if (f.get("name") or "").lower().endswith(".mp4")]
    preferred = next((f for f in mp4_files if "512kb" in f["name"].lower()), None)
    chosen = preferred or (mp4_files[0] if mp4_files else None)
    if not chosen:
        return None
    return f"https://archive.org/download/{identifier}/{chosen['name']}"


# --- NASA Image and Video Library --------------------------------------------------
# No API key required (images-api.nasa.gov is a public, unauthenticated endpoint —
# confirmed with a real request during this session). NASA's own media usage
# guidelines: NASA content is generally not copyrighted unless explicitly noted on an
# individual item — genuinely free, no per-item license check needed the way
# Commons/Europeana/Flickr require, since the agency-wide default already clears the
# bar. Narrow but strong fit specifically for space/aeronautics/science topics.
NASA_IMAGES_API = "https://images-api.nasa.gov/search"


def _nasa_images_search(query: str) -> str | None:
    resp = requests.get(
        NASA_IMAGES_API, headers=HEADERS,
        params={"q": query, "media_type": "image"}, timeout=20,
    )
    resp.raise_for_status()
    items = resp.json().get("collection", {}).get("items", [])
    for item in items[:8]:
        data = (item.get("data") or [{}])[0]
        if not _title_relevant(query, data.get("title", "")):
            continue
        links = item.get("links") or []
        image_link = next((l["href"] for l in links if l.get("render") == "image"), None)
        if image_link:
            return image_link
    return None


# --- Europeana -----------------------------------------------------------------------
# Aggregates many European museum/archive/library collections behind one real API.
# Per-item `rights` metadata is present and MUST be checked per item (confirmed via a
# real query during this session: results genuinely mix CC0/public-domain items with
# CC-BY-NC-ND and outright "In Copyright" ones in the same result set) — same
# discipline as Commons, nothing here is assumed clean just because it's in the index.
# Uses Europeana's own published public demo key ("api2demo", confirmed working
# live this session) when EUROPEANA_API_KEY isn't set — the demo key is real and
# usable, but shared/rate-limited; register a free key at apis.europeana.eu for
# reliable production use (documented in .env.example).
EUROPEANA_API = "https://api.europeana.eu/record/v2/search.json"
EUROPEANA_API_KEY = os.environ.get("EUROPEANA_API_KEY") or "api2demo"

# Rights values that clear a real commercial-use bar — public domain / CC0 / CC-BY /
# CC-BY-SA. Deliberately excludes anything "In Copyright" (rightsstatements.org's
# InC-* codes) and any Creative Commons variant carrying NC (non-commercial) or ND
# (no-derivatives), since Ken Burns pan/zoom + color grading + captions IS a
# derivative work, and this project's own generated videos aren't non-commercial use.
_EUROPEANA_ALLOWED_RIGHTS = (
    "publicdomain/mark", "publicdomain/zero", "cc0",
    "/by/", "/by-sa/",
)


def _europeana_search(query: str) -> str | None:
    resp = requests.get(
        EUROPEANA_API, headers=HEADERS,
        params={
            "wskey": EUROPEANA_API_KEY, "query": query,
            "media": "true", "qf": "TYPE:IMAGE", "rows": 8,
        },
        timeout=20,
    )
    resp.raise_for_status()
    body = resp.json()
    if not body.get("success"):
        return None
    for item in body.get("items", []):
        rights = " ".join(item.get("rights") or []).lower()
        if not any(allowed in rights for allowed in _EUROPEANA_ALLOWED_RIGHTS):
            continue
        title = " ".join(item.get("title") or [])
        if not _title_relevant(query, title):
            continue
        image_url = item.get("edmIsShownBy") or item.get("edmPreview")
        if image_url:
            return image_url[0] if isinstance(image_url, list) else image_url
    return None


# --- Flickr Commons ------------------------------------------------------------------
# "The Commons" — institutional archives (Library of Congress, Smithsonian, national
# archives, etc.) that explicitly upload to Flickr under "no known copyright
# restrictions." Needs a real, free API key (instant self-service signup at
# flickr.com/services/api) — FLICKR_API_KEY absent means this source is silently
# skipped, same graceful-degradation convention as Pexels. NOT live-verified against
# the real API this session (no key available) — implemented against Flickr's
# documented flickr.photos.search response shape; verify with a real key before
# trusting it in production, per this project's own "verify against the real stack"
# rule.
FLICKR_API = "https://api.flickr.com/services/rest/"
FLICKR_API_KEY = os.environ.get("FLICKR_API_KEY", "")


def _flickr_commons_search(query: str) -> str | None:
    if not FLICKR_API_KEY:
        return None
    resp = requests.get(
        FLICKR_API, headers=HEADERS,
        params={
            "method": "flickr.photos.search", "api_key": FLICKR_API_KEY,
            "text": query, "is_commons": "1", "media": "photos",
            "extras": "url_l,url_c,owner_name", "per_page": 8, "format": "json",
            "nojsoncallback": "1",
        },
        timeout=20,
    )
    resp.raise_for_status()
    photos = resp.json().get("photos", {}).get("photo", [])
    for photo in photos:
        if not _title_relevant(query, photo.get("title", "")):
            continue
        image_url = photo.get("url_l") or photo.get("url_c")
        if image_url:
            return image_url
    return None


# --- Google Custom Search (license-filtered image search) ----------------------------
# The legitimate version of "search Google Images": Google's Custom Search JSON API
# supports a `rights` parameter that filters results to actually-licensed images
# (public domain / CC variants) instead of returning arbitrary copyrighted web
# images with no reuse rights, which raw Google Images results would be. Needs both
# GOOGLE_CSE_API_KEY and GOOGLE_CSE_CX (a Custom Search Engine ID configured to
# search the entire web) — free tier is 100 queries/day, paid beyond that. Neither
# credential is available in this environment, so — like Flickr above — this is
# real, documented-API-shaped code, not yet exercised against a live response.
GOOGLE_CSE_API = "https://www.googleapis.com/customsearch/v1"
GOOGLE_CSE_API_KEY = os.environ.get("GOOGLE_CSE_API_KEY", "")
GOOGLE_CSE_CX = os.environ.get("GOOGLE_CSE_CX", "")


def _google_cse_search(query: str) -> str | None:
    if not (GOOGLE_CSE_API_KEY and GOOGLE_CSE_CX):
        return None
    resp = requests.get(
        GOOGLE_CSE_API, headers=HEADERS,
        params={
            "key": GOOGLE_CSE_API_KEY, "cx": GOOGLE_CSE_CX, "q": query,
            "searchType": "image", "rights": "cc_publicdomain|cc_attribute|cc_sharealike",
            "num": 8, "safe": "active",
        },
        timeout=20,
    )
    resp.raise_for_status()
    items = resp.json().get("items", [])
    for item in items:
        if not _title_relevant(query, item.get("title", "")):
            continue
        if item.get("link"):
            return item["link"]
    return None


def _pexels_video_search(query: str) -> str | None:
    if not PEXELS_API_KEY:
        return None
    resp = requests.get(
        PEXELS_VIDEO_API,
        headers={"Authorization": PEXELS_API_KEY},
        params={"query": query, "orientation": "portrait", "per_page": 3, "size": "medium"},
        timeout=20,
    )
    resp.raise_for_status()
    for video in resp.json().get("videos", []):
        files = sorted(video.get("video_files", []), key=lambda f: f.get("width") or 9999)
        for f in files:
            if f.get("file_type") == "video/mp4" and (f.get("width") or 0) >= MIN_VIDEO_WIDTH:
                return f["link"]
    return None


def _pexels_photo_search(query: str) -> str | None:
    if not PEXELS_API_KEY:
        return None
    resp = requests.get(
        PEXELS_PHOTO_API,
        headers={"Authorization": PEXELS_API_KEY},
        params={"query": query, "orientation": "portrait", "per_page": 1},
        timeout=20,
    )
    resp.raise_for_status()
    photos = resp.json().get("photos", [])
    return photos[0]["src"]["large2x"] if photos else None


_FACE_CASCADE = None


def _face_cascade():
    global _FACE_CASCADE
    if _FACE_CASCADE is None:
        _FACE_CASCADE = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
    return _FACE_CASCADE


def _detect_face_center(image_path: Path) -> list[float] | None:
    """(fx, fy) fractions of image width/height for the largest detected face, or None.
    Purely a framing hint for render.py's Ken Burns pan/zoom — never fatal, a detection
    failure just means the renderer falls back to its own default framing."""
    try:
        img = cv2.imread(str(image_path))
        if img is None:
            return None
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        faces = _face_cascade().detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(60, 60))
        if len(faces) == 0:
            return None
        x, y, w, h = max(faces, key=lambda f: f[2] * f[3])  # largest face wins over false positives
        img_h, img_w = img.shape[:2]
        return [(x + w / 2) / img_w, (y + h / 2) / img_h]
    except Exception:
        return None


# A framing GUESS, not a genuine detection — used only when _detect_face_center() fails
# on a "person" beat. haarcascade_frontalface_default is trained on real frontal photos;
# named historical figures sourced via Wikidata P18/Commons are overwhelmingly
# pre-photography imagery — paintings, engravings, coins, marble busts — where detection
# failing is the common case, not the rare one (see OPEN_ISSUES.md audit #35). Falling
# back to a dead-center crop in that case is a worse default than this: the vast majority
# of single-subject portrait/bust compositions place the head in the upper third of the
# frame, not centered, so biasing the Ken Burns crop upward reads as a considered
# portrait crop instead of a generic thumbnail center-crop.
PORTRAIT_FALLBACK_CENTER = (0.5, 0.35)


def _face_or_portrait_fallback(image_path: Path, entity_type: str) -> list[float] | None:
    """_detect_face_center()'s result when it finds one; otherwise, for a "person" beat
    specifically, the documented upper-third framing guess above rather than leaving
    render.py to fall back to its own blind dead-center default. Every other entity_type
    keeps the plain None (a "place"/"event"/"scene" image has no equivalent portrait-
    composition assumption to lean on)."""
    face = _detect_face_center(image_path)
    if face is not None:
        return face
    if entity_type == "person":
        return list(PORTRAIT_FALLBACK_CENTER)
    return None


PLACEHOLDER_PALETTE = [
    ((70, 45, 30), (18, 14, 20)),   # warm ember core -> near-black edge
    ((30, 45, 55), (12, 14, 22)),   # cool teal core -> near-black edge
    ((55, 30, 40), (16, 12, 18)),   # muted wine core -> near-black edge
    ((45, 55, 35), (14, 18, 12)),   # muted olive/moss core -> near-black edge
    ((35, 35, 60), (12, 12, 20)),   # deep indigo core -> near-black edge
    ((60, 50, 25), (20, 16, 10)),   # aged brass/sepia core -> near-black edge
]

# Warm palettes (ember/wine/brass) read as "human" and cool ones (teal/olive/indigo) as
# "place/time" — a deliberate, not arbitrary, split used to bias illustrated-mode's
# palette choice by entity_type (see _illustrated_seed) rather than picking blind.
_WARM_PALETTE_INDICES = (0, 2, 5)
_COOL_PALETTE_INDICES = (1, 3, 4)


def _placeholder_clip(out_path: Path, seed: int, duration: float = 4.0, fps: int = 30) -> None:
    """Last-resort background when every real source misses for a beat — a genuinely
    ANIMATED backdrop (the vignette's center drifts in a slow ellipse and a soft
    diagonal light sweep drifts across the frame, on top of film grain), not a still
    image that then just gets the same Ken Burns pan as everything else. Per the user's
    explicit direction: a placeholder should read as a deliberate motion-graphics
    choice, not a flat/frozen fallback. Rendered frame-by-frame in numpy (full creative
    control over how the drift/sweep actually look) and piped straight into ffmpeg as
    raw video, rather than trying to express organic motion through ffmpeg's own filter
    expressions. Saved as an .mp4 so render.py treats it exactly like any other stock
    video clip (its VIDEO_EXTS branch), no special-casing needed there. Still honest
    about being a fallback: no attempt to fake photographic content."""
    w, h = 1080, 1920
    core, edge = PLACEHOLDER_PALETTE[seed % len(PLACEHOLDER_PALETTE)]
    core_arr = np.array(core, dtype=np.float32)
    edge_arr = np.array(edge, dtype=np.float32)
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    rng = np.random.default_rng(seed)
    n_frames = max(1, round(duration * fps))

    cmd = [
        "ffmpeg", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{w}x{h}", "-r", str(fps),
        "-i", "-", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "20", str(out_path),
    ]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for i in range(n_frames):
            phase = i / n_frames
            # The vignette's own center drifts in a small ellipse over the clip's
            # duration instead of sitting still — this alone is what turns a static
            # radial gradient into something that reads as deliberately animated.
            cx = w * (0.5 + 0.05 * math.sin(phase * 2 * math.pi))
            cy = h * (0.38 + 0.035 * math.cos(phase * 2 * math.pi))
            dist = np.sqrt(((xx - cx) / (w * 0.75)) ** 2 + ((yy - cy) / (h * 0.55)) ** 2)
            t = np.clip(dist, 0, 1)[..., None]
            rgb = core_arr * (1 - t) + edge_arr * t

            # A soft diagonal light sweep oscillating back and forth — driven by sin(),
            # not a modulo wrap, specifically so it's C0-continuous at the loop point:
            # render.py plays this with -stream_loop -1 for beats longer than `duration`,
            # so anything that isn't truly periodic would visibly jump every repeat.
            diag = (xx / w + yy / h) / 2
            sweep_pos = 0.5 + 0.65 * math.sin(phase * 2 * math.pi)
            sweep = np.clip(1 - np.abs(diag - sweep_pos) * 6, 0, 1)[..., None] * 16
            rgb = rgb + sweep

            grain = rng.normal(0, 3.0, size=(h, w, 1)).astype(np.float32)
            frame = np.clip(rgb + grain, 0, 255).astype(np.uint8)
            proc.stdin.write(np.ascontiguousarray(frame).tobytes())
    finally:
        proc.stdin.close()
        proc.wait()


def _download(url: str, max_retries: int = 3) -> bytes | None:
    for attempt in range(max_retries):
        try:
            resp = requests.get(url, headers=HEADERS, timeout=60)
            if resp.status_code == 429:
                wait = float(resp.headers.get("Retry-After", 2 * (attempt + 1)))
                time.sleep(wait)
                continue
            resp.raise_for_status()
            return resp.content
        except requests.exceptions.RequestException:
            if attempt == max_retries - 1:
                return None
            time.sleep(1.5 * (attempt + 1))
    return None


def _save_image(url: str, out_base: Path, source: str, entity_type: str) -> dict | None:
    content = _download(url)
    if not content:
        return None
    path = out_base.with_suffix(".jpg")
    path.write_bytes(content)
    return {"path": path, "source": source, "entity_type": entity_type, "face": _face_or_portrait_fallback(path, entity_type)}


def _first_image_hit(query: str, sources: list[tuple]) -> tuple[str | None, str | None]:
    """Tries each (search_fn, source_name) pair in order, isolating each source's own
    network/API failure so one source's hiccup doesn't skip every source after it — a
    real latent bug the single shared try/except this replaces had: previously,
    Commons raising a RequestException silently skipped Pexels photo too, not just
    Commons, since both sat inside one try block. Each source here fails independently
    instead."""
    for search_fn, source_name in sources:
        try:
            image_url = search_fn(query)
        except requests.exceptions.RequestException:
            continue
        if image_url:
            return image_url, source_name
    return None, None


def _fetch_person(query: str, out_base: Path, seed: int, entity_type: str) -> dict:
    try:
        portrait_url = _wikidata_portrait(query)
    except requests.exceptions.RequestException:
        portrait_url = None
    if portrait_url:
        asset = _save_image(portrait_url, out_base, "wikidata", entity_type)
        if asset:
            return asset

    for candidate in _name_candidates(query):
        try:
            image_url = _commons_search(candidate)
        except requests.exceptions.RequestException:
            image_url = None
        if image_url:
            asset = _save_image(image_url, out_base, "commons", entity_type)
            if asset:
                return asset

    # Beyond Wikidata/Commons: real, license-checked general-purpose image search —
    # deliberately NOT Pexels here either (see this function's own header comment on
    # why: generic modern-stock photography of anonymous models is the wrong fallback
    # for a NAMED historical figure). Europeana/Flickr Commons/Google CSE can
    # plausibly surface an actual portrait Commons' own search missed; NASA is
    # intentionally excluded here (space-agency imagery has no bearing on a person
    # portrait search).
    image_url, source = _first_image_hit(query, [
        (_europeana_search, "europeana"),
        (_flickr_commons_search, "flickr_commons"),
        (_google_cse_search, "google_cse"),
    ])
    if image_url:
        asset = _save_image(image_url, out_base, source, entity_type)
        if asset:
            return asset

    path = out_base.with_suffix(".mp4")
    _placeholder_clip(path, seed)
    return {"path": path, "source": "placeholder", "entity_type": entity_type, "face": None}


def _fetch_generic(query: str, out_base: Path, seed: int, entity_type: str) -> dict:
    # Internet Archive's public-domain film collections tried FIRST, before generic
    # Pexels stock — real period-appropriate historical footage (when it exists and
    # passes the relevance gate) belongs in a documentary ahead of generic modern
    # stock video of the same subject. Falls straight through to the existing waterfall
    # below on any miss (no match, no license-clean match, no relevant match, or a
    # network error) — this is purely additive, never a harder failure mode than before.
    try:
        archive_id = _archive_org_search(query)
        archive_url = _archive_org_video_url(archive_id) if archive_id else None
    except requests.exceptions.RequestException:
        archive_url = None
    if archive_url:
        content = _download(archive_url)
        if content:
            path = out_base.with_suffix(".mp4")
            path.write_bytes(content)
            return {"path": path, "source": "archive_org", "entity_type": entity_type, "face": None}

    try:
        video_url = _pexels_video_search(query)
    except requests.exceptions.RequestException:
        video_url = None
    if video_url:
        content = _download(video_url)
        if content:
            path = out_base.with_suffix(".mp4")
            path.write_bytes(content)
            return {"path": path, "source": "video", "entity_type": entity_type, "face": None}

    # Real archival/institutional sources tried before generic modern stock — the same
    # visual-evidence-hierarchy reasoning as the Internet Archive section above
    # (primary/archival evidence belongs ahead of anonymous stock of the same
    # subject). Pexels photo stays last resort, not removed.
    image_url, source = _first_image_hit(query, [
        (_commons_search, "commons"),
        (_nasa_images_search, "nasa"),
        (_europeana_search, "europeana"),
        (_flickr_commons_search, "flickr_commons"),
        (_google_cse_search, "google_cse"),
        (_pexels_photo_search, "pexels_photo"),
    ])
    if image_url:
        asset = _save_image(image_url, out_base, source, entity_type)
        if asset:
            return asset

    path = out_base.with_suffix(".mp4")
    _placeholder_clip(path, seed)
    return {"path": path, "source": "placeholder", "entity_type": entity_type, "face": None}


def _illustrated_seed(index: int, entity_type: str) -> int:
    """Picks a PLACEHOLDER_PALETTE index for illustrated-mode's graphic backdrop —
    biased warm for "person" beats, cool for everything else (see the palette-index
    comment above), with the beat's own position mixed in so consecutive beats of the
    same entity_type still get visibly different palettes rather than repeating."""
    bucket = _WARM_PALETTE_INDICES if entity_type == "person" else _COOL_PALETTE_INDICES
    return bucket[index % len(bucket)]


def _fetch_illustrated(out_base: Path, seed: int, entity_type: str, visual_query: str = "") -> dict:
    """Style == "illustrated" (see Claude outputs/OPEN_ISSUES.md #56/#61 and
    PROFESSIONAL_QUALITY_ROADMAP.md §7 item 12's genre-strategy question — the user's
    answer was to keep *both* the photographic-documentary approach and a motion-
    graphics-forward one, and let the person generating a video choose).

    Tries a real, locally-generated flat-vector illustration first (pipeline/
    illustrate.py) when a GPU is actually present — a real per-beat image, not just a
    colored backdrop. Falls back to the same animated graphic backdrop used as
    photographic mode's honest, verified sourcing-failure fallback (_placeholder_clip —
    see #16) whenever GPU generation isn't available or fails for any reason (no GPU on
    this host, model load failure, OOM, ...) — every failure mode there returns cleanly,
    so this never has to guess whether it's safe to fall back. No Wikidata/Commons/
    Pexels calls either way. `source` distinguishes which path actually produced the
    asset ("illustrated_gpu" vs. "illustrated") for logging/debugging."""
    if illustrate.gpu_illustration_available():
        image_path = out_base.with_suffix(".png")
        prompt = illustrate.illustration_prompt(visual_query, entity_type)
        if illustrate.generate_illustration(prompt, image_path, seed=seed):
            return {"path": image_path, "source": "illustrated_gpu", "entity_type": entity_type, "face": None}

    path = out_base.with_suffix(".mp4")
    _placeholder_clip(path, _illustrated_seed(seed, entity_type))
    return {"path": path, "source": "illustrated", "entity_type": entity_type, "face": None}


def fetch_one(beat: dict, out_base: Path, seed: int, style: str = "photographic") -> dict:
    """Returns {"path": Path, "source": str, "entity_type": str, "face": [fx,fy]|None}.
    style: "photographic" (default — real sourced imagery/stock, unchanged behavior) or
    "illustrated" (see _fetch_illustrated)."""
    entity_type = beat.get("entity_type", "scene")
    if style == "illustrated":
        return _fetch_illustrated(out_base, seed, entity_type, beat.get("visual_query", ""))
    query = beat["visual_query"]
    if entity_type == "person":
        return _fetch_person(query, out_base, seed, entity_type)
    return _fetch_generic(query, out_base, seed, entity_type)


def fetch_all(out_dir: str, beats: list[dict], style: str = "photographic") -> list[dict]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    assets = []
    for i, beat in enumerate(beats):
        if i > 0 and style != "illustrated":
            time.sleep(0.8)  # be a polite API citizen, avoid rate limits — no external
            # calls happen in illustrated mode, so there's nothing to be polite to.
        base = out / f"img_{i:02d}"
        asset = fetch_one(beat, base, i, style=style)
        print(f"[{asset['source']}] {beat['visual_query']!r} ({asset['entity_type']}) -> {asset['path']}", file=sys.stderr)
        asset["path"] = str(asset["path"])
        assets.append(asset)
    return assets


if __name__ == "__main__":
    out_dir = sys.argv[1]
    beats = [{"visual_query": q, "entity_type": "scene"} for q in sys.argv[2:]]
    for asset in fetch_all(out_dir, beats):
        print(asset["path"])
