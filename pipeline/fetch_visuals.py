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
import math
import os
import subprocess
import sys
import time
from pathlib import Path

import cv2
import numpy as np
import requests
from PIL import Image

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


PLACEHOLDER_PALETTE = [
    ((70, 45, 30), (18, 14, 20)),   # warm ember core -> near-black edge
    ((30, 45, 55), (12, 14, 22)),   # cool teal core -> near-black edge
    ((55, 30, 40), (16, 12, 18)),   # muted wine core -> near-black edge
]


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

    for candidate in _name_candidates(query):
        try:
            image_url = _commons_search(candidate)
        except requests.exceptions.RequestException:
            image_url = None
        if image_url:
            asset = _save_image(image_url, out_base, "commons", entity_type)
            if asset:
                return asset

    path = out_base.with_suffix(".mp4")
    _placeholder_clip(path, seed)
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

    path = out_base.with_suffix(".mp4")
    _placeholder_clip(path, seed)
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
