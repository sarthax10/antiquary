#!/usr/bin/env python3
"""Fetch real visuals for a video — actual filmed stock footage where a query matches
something filmable, real archival images (Wikimedia Commons) for things only paintings/
artifacts can show, otherwise a plain gradient as a last resort. Free, no paid tier needed.

Usage: fetch_visuals.py <out_dir> "<query 1>" "<query 2>" ...
One asset is fetched per query, saved as <out_dir>/img_00.<ext>, img_01.<ext>, ... where
<ext> is .mp4 for real video or .jpg for a still image — render.py tells them apart by
extension. Queries that return nothing usable are skipped (not padded).

Source order per query: Pexels Video (real motion, needs PEXELS_API_KEY) -> Wikimedia
Commons image (no key needed, best fit for historical figures/art/artifacts) -> Pexels
Photo (needs PEXELS_API_KEY) -> gradient placeholder.
"""
import os
import sys
import time
from pathlib import Path

import requests
from PIL import Image, ImageDraw

COMMONS_API = "https://commons.wikimedia.org/w/api.php"
PEXELS_VIDEO_API = "https://api.pexels.com/videos/search"
PEXELS_PHOTO_API = "https://api.pexels.com/v1/search"
HEADERS = {"User-Agent": "history-shorts-local-project/0.1 (personal hobby project)"}
PEXELS_API_KEY = os.environ.get("PEXELS_API_KEY", "")

MIN_IMAGE_WIDTH = 500
MIN_VIDEO_WIDTH = 480
ALLOWED_IMAGE_MIME = {"image/jpeg", "image/png"}


def _commons_search(query: str) -> str | None:
    resp = requests.get(
        COMMONS_API,
        headers=HEADERS,
        params={
            "action": "query",
            "generator": "search",
            "gsrnamespace": 6,
            "gsrsearch": query,
            "gsrlimit": 10,
            "prop": "imageinfo",
            "iiprop": "url|size|mime",
            "format": "json",
        },
        timeout=20,
    )
    resp.raise_for_status()
    pages = resp.json().get("query", {}).get("pages", {})
    candidates = sorted(pages.values(), key=lambda p: p.get("index", 999))
    for page in candidates:
        info = (page.get("imageinfo") or [None])[0]
        if not info or info.get("mime") not in ALLOWED_IMAGE_MIME:
            continue
        if info.get("width", 0) < MIN_IMAGE_WIDTH:
            continue
        return info["url"]
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


def fetch_one(query: str, out_base: Path, seed: int) -> tuple[Path, str]:
    """Returns (path, source) where source is one of video/commons/pexels_photo/placeholder."""
    try:
        video_url = _pexels_video_search(query)
    except requests.exceptions.RequestException:
        video_url = None
    if video_url:
        content = _download(video_url)
        if content:
            path = out_base.with_suffix(".mp4")
            path.write_bytes(content)
            return path, "video"

    try:
        image_url = _commons_search(query)
        source = "commons"
        if not image_url:
            image_url = _pexels_photo_search(query)
            source = "pexels_photo"
    except requests.exceptions.RequestException:
        image_url, source = None, None
    if image_url:
        content = _download(image_url)
        if content:
            path = out_base.with_suffix(".jpg")
            path.write_bytes(content)
            return path, source

    path = out_base.with_suffix(".jpg")
    _placeholder(path, seed)
    return path, "placeholder"


def fetch_all(out_dir: str, queries: list[str]) -> list[str]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    paths = []
    for i, q in enumerate(queries):
        if i > 0:
            time.sleep(0.8)  # be a polite API citizen, avoid rate limits
        base = out / f"img_{i:02d}"
        path, source = fetch_one(q, base, i)
        print(f"[{source}] {q!r} -> {path}", file=sys.stderr)
        paths.append(str(path))
    return paths


if __name__ == "__main__":
    out_dir = sys.argv[1]
    queries = sys.argv[2:]
    for path in fetch_all(out_dir, queries):
        print(path)
