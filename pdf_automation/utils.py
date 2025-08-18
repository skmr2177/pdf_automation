import hashlib
import os
import re
from pathlib import Path
from typing import Iterable, List, Optional, Set, Tuple

from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse, urlunparse, parse_qsl, urlencode


TRACKING_PARAMS = {"utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content", "gclid", "fbclid"}


def compute_sha256(text: str) -> str:
    hasher = hashlib.sha256()
    hasher.update(text.encode("utf-8", errors="ignore"))
    return hasher.hexdigest()


def normalize_url(raw_url: str) -> str:
    parsed = urlparse(raw_url)
    scheme = parsed.scheme.lower() or "https"
    netloc = parsed.netloc.lower()
    path = parsed.path or "/"
    # Normalize trailing slash (no double slashes, keep root as "/")
    if path != "/" and path.endswith("/"):
        path = path[:-1]

    # Remove fragments
    fragment = ""

    # Remove common tracking query params, preserve order for determinism
    query_pairs = [(k, v) for k, v in parse_qsl(parsed.query, keep_blank_values=True) if k not in TRACKING_PARAMS]
    query = urlencode(query_pairs)

    normalized = urlunparse((scheme, netloc, path, "", query, fragment))
    return normalized


def resolve_url(base_url: str, href: str) -> Optional[str]:
    if not href:
        return None
    if href.startswith(("mailto:", "tel:", "javascript:", "data:")):
        return None
    try:
        absolute = urljoin(base_url, href)
        return normalize_url(absolute)
    except Exception:
        return None


def is_internal_url(url: str, allowed_host: str) -> bool:
    try:
        return urlparse(url).netloc == allowed_host
    except Exception:
        return False


def sanitize_path_segment(segment: str) -> str:
    # Replace characters that are unsafe on filesystems
    return re.sub(r"[^A-Za-z0-9._-]", "_", segment)


def url_to_pdf_path(abs_url: str, out_root: Path) -> Path:
    parsed = urlparse(abs_url)
    netloc = sanitize_path_segment(parsed.netloc)
    path = parsed.path or "/"
    if path == "/":
        path = "/index"
    # Remove trailing slash if any
    if path.endswith("/"):
        path = path[:-1]
    # Build relative path mirroring site structure
    segments = [sanitize_path_segment(s) for s in path.split("/") if s]
    rel_path = Path(netloc).joinpath(*segments).with_suffix(".pdf")
    return out_root / rel_path


def make_relative_href(current_pdf: Path, target_pdf: Path) -> str:
    return os.path.relpath(target_pdf, start=current_pdf.parent)


def extract_links(html: str, base_url: str) -> List[str]:
    soup = BeautifulSoup(html, "lxml")
    results: List[str] = []
    for a in soup.find_all("a", href=True):
        resolved = resolve_url(base_url, a.get("href"))
        if resolved:
            results.append(resolved)
    # Deduplicate while preserving order
    seen: Set[str] = set()
    unique: List[str] = []
    for u in results:
        if u not in seen:
            seen.add(u)
            unique.append(u)
    return unique


def clean_main_content(full_html: str) -> str:
    soup = BeautifulSoup(full_html, "lxml")

    # Prefer known main containers
    main = soup.select_one("main, article, [role='main'], .article, .content, .content-area")
    if not main:
        main = soup.body or soup

    # Remove unwanted elements (navigation, banners, footers, scripts)
    for sel in [
        "header", "nav", "footer", ".toc", ".cookie", ".banner", ".ads", ".share",
        ".breadcrumbs", ".feedback", "script", "noscript", "style", "iframe", "button",
        "form", ".newsletter", ".social", ".sidebar", "aside",
    ]:
        for el in main.select(sel):
            el.decompose()

    # Normalize heading levels: ensure a single H1
    headings = main.find_all(["h1", "h2", "h3", "h4"]) if hasattr(main, "find_all") else []
    seen_h1 = False
    for h in headings:
        name = h.name.lower()
        if name == "h1":
            if seen_h1:
                h.name = "h2"
            else:
                seen_h1 = True
        elif name in {"h4"}:
            h.name = "h3"

    # Remove empty elements
    for el in list(main.find_all(True)):
        if not el.get_text(strip=True) and not el.find("img"):
            # Keep if it contributes layout (like pre/code even if empty)
            if el.name not in {"pre", "code", "table", "img", "svg"}:
                el.decompose()

    # Build minimal HTML document
    html = BeautifulSoup("<html><head></head><body></body></html>", "lxml")
    body = html.body
    title_tag = soup.find("title")
    page_title = title_tag.get_text(strip=True) if title_tag else "Document"
    h1 = html.new_tag("h1")
    h1.string = page_title
    body.append(h1)

    # Append cleaned main content children
    for child in list(main.children):
        body.append(child)

    return str(html)

