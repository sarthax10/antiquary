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
  matching the query) -> Wikimedia Commons keyword search -> gradient placeholder.
  Deliberately NO Pexels fallback here — Pexels is generic modern stock photography of
  anonymous models, and using it to stand in for a specific named historical figure is
  exactly the "random dude" problem this beat-level sourcing exists to avoid. An honest
  abstract placeholder is less misleading than the wrong face.
- everything else: Pexels Video (real motion, needs PEXELS_API_KEY) -> Wikimedia Commons
  image -> Pexels Photo (needs PEXELS_API_KEY) -> gradient placeholder.
"""
import os
import sys
import time
from pathlib import Path

import cv2
import requests
from PIL import Image, ImageDraw

COMMONS_API = "https://commons.wikimedia.org/w/api.php"
WIKIDATA_API = "https://www.wikidata.org/w/api.php"
PEXELS_VIDEO_API = "https://api.pexels.com/videos/search"
PEXELS_PHOTO_API = "https://api.pexels.com/v1/search"
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


# Wikidata's wbsearchentities does an entity-name match, not full-text search — a
# visual_query like "Albert Einstein portrait" (the trailing descriptor is deliberately
# there, it's what makes the SAME query work well against Commons/Pexels) returns no
# hits at all, even though "Albert Einstein" alone matches immediately. Stripped as a
# fallback, not the primary attempt, since most beat queries are already just a name.
_PORTRAIT_DESCRIPTORS = {
    "portrait", "photo", "photograph", "statue", "bust", "painting", "engraving",
    "illustration", "drawing", "sketch", "picture", "image", "likeness", "photograph,",
}


def _strip_descriptor(query: str) -> str:
    words = query.split()
    while len(words) > 1 and words[-1].lower().strip(".,") in _PORTRAIT_DESCRIPTORS:
        words = words[:-1]
    return " ".join(words)


def _wikidata_qid(name: str) -> str | None:
    resp = requests.get(
        WIKIDATA_API,
        headers=HEADERS,
        params={"action": "wbsearchentities", "search": name, "language": "en", "type": "item", "limit": 1, "format": "json"},
        timeout=20,
    )
    resp.raise_for_status()
    hits = resp.json().get("search") or []
    return hits[0]["id"] if hits else None


def _wikidata_portrait(name: str) -> str | None:
    """The Wikidata item most closely matching `name`, then its P18 ("image") claim,
    resolved to an actual Commons file URL. None at any step (no matching item, no P18
    claim, image too small/wrong type) falls through to the Commons keyword search."""
    qid = _wikidata_qid(name)
    if not qid:
        stripped = _strip_descriptor(name)
        if stripped != name:
            qid = _wikidata_qid(stripped)
    if not qid:
        return None

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


def _placeholder(out_path: Path, seed: int) -> None:
    w, h = 1080, 1920
    img = Image.new("RGB", (w, h))
    draw = ImageDraw.Draw(img)
    palette = [((30, 25, 45), (90, 60, 40)), ((20, 30, 40), (60, 40, 70)), ((35, 20, 20), (70, 55, 30))]
    top, bottom = palette[seed % len(palette)]
    for y in range(h):
        t = y / h
        rgb = tuple(int(top[i] + (bottom[i] - top[i]) * t) for i in range(3))
        draw.line([(0, y), (w, y)], fill=rgb)
    img.save(out_path, quality=90)


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
    return {"path": path, "source": source, "entity_type": entity_type, "face": _detect_face_center(path)}


def _fetch_person(query: str, out_base: Path, seed: int, entity_type: str) -> dict:
    try:
        portrait_url = _wikidata_portrait(query)
    except requests.exceptions.RequestException:
        portrait_url = None
    if portrait_url:
        asset = _save_image(portrait_url, out_base, "wikidata", entity_type)
        if asset:
            return asset

    try:
        image_url = _commons_search(query)
    except requests.exceptions.RequestException:
        image_url = None
    if image_url:
        asset = _save_image(image_url, out_base, "commons", entity_type)
        if asset:
            return asset

    path = out_base.with_suffix(".jpg")
    _placeholder(path, seed)
    return {"path": path, "source": "placeholder", "entity_type": entity_type, "face": None}


def _fetch_generic(query: str, out_base: Path, seed: int, entity_type: str) -> dict:
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

    try:
        image_url = _commons_search(query)
        source = "commons"
        if not image_url:
            image_url = _pexels_photo_search(query)
            source = "pexels_photo"
    except requests.exceptions.RequestException:
        image_url, source = None, None
    if image_url:
        asset = _save_image(image_url, out_base, source, entity_type)
        if asset:
            return asset

    path = out_base.with_suffix(".jpg")
    _placeholder(path, seed)
    return {"path": path, "source": "placeholder", "entity_type": entity_type, "face": None}


def fetch_one(beat: dict, out_base: Path, seed: int) -> dict:
    """Returns {"path": Path, "source": str, "entity_type": str, "face": [fx,fy]|None}."""
    query = beat["visual_query"]
    entity_type = beat.get("entity_type", "scene")
    if entity_type == "person":
        return _fetch_person(query, out_base, seed, entity_type)
    return _fetch_generic(query, out_base, seed, entity_type)


def fetch_all(out_dir: str, beats: list[dict]) -> list[dict]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    assets = []
    for i, beat in enumerate(beats):
        if i > 0:
            time.sleep(0.8)  # be a polite API citizen, avoid rate limits
        base = out / f"img_{i:02d}"
        asset = fetch_one(beat, base, i)
        print(f"[{asset['source']}] {beat['visual_query']!r} ({asset['entity_type']}) -> {asset['path']}", file=sys.stderr)
        asset["path"] = str(asset["path"])
        assets.append(asset)
    return assets


if __name__ == "__main__":
    out_dir = sys.argv[1]
    beats = [{"visual_query": q, "entity_type": "scene"} for q in sys.argv[2:]]
    for asset in fetch_all(out_dir, beats):
        print(asset["path"])
