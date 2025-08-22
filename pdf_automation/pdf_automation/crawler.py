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


def _is_same_host(url: str, allowed_prefix: str) -> bool:
    """Return True if url shares the same host as allowed_prefix."""
    try:
        from urllib.parse import urlparse
        return urlparse(url).netloc.lower() == urlparse(allowed_prefix).netloc.lower()
    except Exception:
        return False


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


def _ensure_absolute_allowed_prefix(seed_url: str, allowed_prefix: str) -> str:
    """Return an absolute allowed_prefix.

    If allowed_prefix starts with '/', treat it as a path under the seed's origin.
    """
    try:
        from urllib.parse import urlparse
    except Exception:
        return allowed_prefix
    if not allowed_prefix:
        return allowed_prefix
    if allowed_prefix.startswith("http://") or allowed_prefix.startswith("https://"):
        return allowed_prefix.rstrip("/")
    if allowed_prefix.startswith("/"):
        seed = urlparse(seed_url)
        origin = f"{seed.scheme}://{seed.netloc}"
        return (origin + allowed_prefix).rstrip("/")
    # Fallback: assume it's already absolute-like
    return allowed_prefix.rstrip("/")


def collect_internal_urls(seed_url: str, allowed_prefix: str, max_pages: int | None = None) -> Set[str]:
    """Collect all pages that ultimately land under allowed_prefix, following redirects on the same host.

    - Enqueue any link on the same host as allowed_prefix
    - After fetching a URL, only mark as visited if the final URL (after redirects) starts with allowed_prefix
    - Unlimited depth; optional max_pages cap
    """
    seed_url = _normalize_url(seed_url)
    # Normalize allowed_prefix: allow path-only inputs like "/en/3d-warehouse"
    allowed_prefix = _ensure_absolute_allowed_prefix(seed_url, allowed_prefix)
    allowed_prefix = _normalize_url(allowed_prefix)

    visited: Set[str] = set()
    queue: deque[str] = deque([seed_url])

    headers = {
        # Pretend to be a recent stable Chrome on Linux to avoid bot pages
        "User-Agent": (
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
    }

    while queue:
        if max_pages is not None and len(visited) >= max_pages:
            break
        current = queue.popleft()
        current = _normalize_url(current)
        if not _is_same_host(current, allowed_prefix):
            continue

        try:
            resp = requests.get(current, headers=headers, timeout=30, allow_redirects=True)
            resp.raise_for_status()
            final_url = _normalize_url(resp.url)
            html = resp.text
        except Exception:
            continue

        # Only accept pages that end up under the allowed prefix
        if not _is_internal_allowed(final_url, allowed_prefix):
            continue

        if final_url in visited:
            continue
        visited.add(final_url)

        # Extract links relative to the final URL
        for href in _extract_links(html):
            abs_url = _absolutize(href, final_url)
            abs_url = _normalize_url(abs_url)
            if not abs_url:
                continue
            if not _is_same_host(abs_url, allowed_prefix):
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
    weasyprint = None
    try:
        from weasyprint import HTML  # type: ignore
        weasyprint = HTML
    except Exception:
        weasyprint = None

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
    }

    for url in urls:
        if not _is_internal_allowed(url, allowed_prefix):
            continue
        relative = url[len(allowed_prefix) :].strip("/")
        safe_relative = relative.replace("?", "_").replace("&", "_")
        if not safe_relative:
            safe_relative = "index"
        pdf_path = output_root_path / (safe_relative + ".pdf")
        pdf_path.parent.mkdir(parents=True, exist_ok=True)

        # Fetch HTML upfront to avoid anti-bot differences when printing
        html: str | None = None
        final_url = url
        try:
            r = requests.get(url, headers=headers, timeout=30, allow_redirects=True)
            r.raise_for_status()
            final_url = _normalize_url(r.url)
            html = r.text
        except Exception:
            html = None

        if chrome and html:
            # Write a temporary local HTML with a <base> tag so relative paths resolve
            tmp_html = pdf_path.with_suffix(".__tmp__.html")
            try:
                soup = BeautifulSoup(html, "html.parser")
                head = soup.find("head")
                if head is None:
                    head = soup.new_tag("head")
                    if soup.contents:
                        soup.insert(0, head)
                    else:
                        soup.append(head)
                # Prepend/replace base tag
                base_tag = soup.new_tag("base", href=final_url)
                # Put base first in head
                head.insert(0, base_tag)
                tmp_html.write_text(str(soup), encoding="utf-8")
                cmd = [
                    chrome,
                    "--headless=new",
                    "--disable-gpu",
                    f"--print-to-pdf={pdf_path}",
                    str(tmp_html),
                ]
                try:
                    subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                finally:
                    try:
                        tmp_html.unlink(missing_ok=True)  # type: ignore[call-arg]
                    except Exception:
                        pass
            except Exception:
                # Fall back to direct URL if local render fails
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
                    pass
        elif weasyprint and html:
            try:
                weasyprint(string=html, base_url=final_url).write_pdf(str(pdf_path))  # type: ignore
            except Exception:
                pass
        elif chrome:
            # Last resort: print direct URL
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
                pass

        # Record mapping whether or not rendering succeeded; file presence indicates success
        url_to_pdf[url] = str(pdf_path)
    return url_to_pdf

