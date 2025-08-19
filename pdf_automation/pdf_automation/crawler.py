import asyncio
import re
import subprocess
import shutil
from collections import deque
from pathlib import Path
from typing import Dict, Iterable, Set

import requests
from bs4 import BeautifulSoup


def _is_internal_allowed(url: str, allowed_prefix: str) -> bool:
    return url.startswith(allowed_prefix)


def _normalize_url(url: str) -> str:
    # Drop URL fragments and normalize trailing slashes
    base = url.split("#", 1)[0]
    if base.endswith("/"):
        base = base.rstrip("/")
    return base


def _absolutize(href: str, base: str) -> str:
    if not href:
        return ""
    if href.startswith("http://") or href.startswith("https://"):
        return href
    if href.startswith("//"):
        # Scheme-relative, assume https
        return "https:" + href
    if href.startswith("/"):
        # Absolute path on same host as base
        # Extract scheme+host from base
        m = re.match(r"^(https?://[^/]+)", base)
        if not m:
            return ""
        return m.group(1) + href
    # Relative path
    if base.endswith("/"):
        return base + href
    else:
        return base.rsplit("/", 1)[0] + "/" + href


def collect_internal_urls(seed_url: str, allowed_prefix: str, max_pages: int | None = None) -> Set[str]:
    seed_url = _normalize_url(seed_url)
    allowed_prefix = _normalize_url(allowed_prefix)

    visited: Set[str] = set()
    queue: deque[str] = deque([seed_url])

    headers = {
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    }

    while queue:
        if max_pages is not None and len(visited) >= max_pages:
            break
        current = queue.popleft()
        current = _normalize_url(current)
        if current in visited:
            continue
        if not _is_internal_allowed(current, allowed_prefix):
            continue

        try:
            resp = requests.get(current, headers=headers, timeout=20)
            resp.raise_for_status()
            html = resp.text
        except Exception:
            continue

        visited.add(current)

        for href in _extract_links(html):
            abs_url = _absolutize(href, current)
            abs_url = _normalize_url(abs_url)
            if not abs_url:
                continue
            if not _is_internal_allowed(abs_url, allowed_prefix):
                continue
            if abs_url not in visited:
                queue.append(abs_url)

    return visited


def _extract_links(html: str) -> Iterable[str]:
    soup = BeautifulSoup(html, "html.parser")
    for a in soup.find_all("a", href=True):
        yield a["href"].strip()


def _find_chrome_binary() -> str | None:
    for name in (
        "google-chrome",
        "google-chrome-stable",
        "chromium-browser",
        "chromium",
        "chrome",
    ):
        binary = shutil.which(name)
        if binary:
            return binary
    return None


async def render_urls_to_pdf(urls: Iterable[str], output_root: str, allowed_prefix: str) -> Dict[str, str]:
    output_root_path = Path(output_root)
    url_to_pdf: Dict[str, str] = {}
    chrome = _find_chrome_binary()
    for url in urls:
        if not _is_internal_allowed(url, allowed_prefix):
            continue
        relative = url[len(allowed_prefix) :].strip("/")
        safe_relative = relative.replace("?", "_").replace("&", "_")
        if not safe_relative:
            safe_relative = "index"
        pdf_path = output_root_path / (safe_relative + ".pdf")
        pdf_path.parent.mkdir(parents=True, exist_ok=True)
        if chrome:
            cmd = [
                chrome,
                "--headless=new",
                "--disable-gpu",
                f"--print-to-pdf={pdf_path}",
                url,
            ]
            try:
                subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            except Exception:
                # Skip on failure
                pass
        # Record mapping whether or not rendering succeeded; file presence indicates success
        url_to_pdf[url] = str(pdf_path)
    return url_to_pdf

