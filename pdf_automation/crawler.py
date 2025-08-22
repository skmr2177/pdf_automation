import os
from collections import deque
from typing import Dict, Iterable, Set, Tuple

import requests
from bs4 import BeautifulSoup

from .utils import normalize_url, url_to_pdf_relpath


class SiteCrawler:
	"""Breadth-first crawler to collect internal HTML pages.

	Builds a manifest of URL -> relative PDF path locations.
	"""

	def __init__(self, start_url: str, same_origin_only: bool = True, max_pages: int | None = None, allowed_prefix: str | None = None):
		self.start_url = normalize_url(start_url, "")
		self.same_origin_only = same_origin_only
		self.max_pages = max_pages
		# If provided, restrict accepted pages to this prefix (after redirects)
		if allowed_prefix is None:
			self.allowed_prefix = None
		else:
			# Support path-only prefixes like "/en/3d-warehouse" by resolving against the seed origin
			from urllib.parse import urlparse
			ap = allowed_prefix.strip()
			if ap.startswith("/"):
				seed = urlparse(self.start_url)
				origin = f"{seed.scheme}://{seed.netloc}"
				self.allowed_prefix = normalize_url(origin, ap)
			else:
				self.allowed_prefix = normalize_url(ap, "")

	def _is_internal(self, base_url: str, target_url: str) -> bool:
		if not self.same_origin_only:
			return True
		from urllib.parse import urlparse
		b = urlparse(base_url)
		t = urlparse(target_url)
		if (b.scheme, b.hostname) == (t.scheme, t.hostname):
			return True
		# If an allowed_prefix was provided, also accept links on that host
		if self.allowed_prefix:
			ap = urlparse(self.allowed_prefix)
			return (ap.scheme, ap.hostname) == (t.scheme, t.hostname)
		return False

	def _is_allowed(self, url: str) -> bool:
		if self.allowed_prefix is None:
			return True
		# accept if normalized URL starts with the allowed prefix
		return url.startswith(self.allowed_prefix)

	def _looks_like_error_page(self, html: str) -> bool:
		try:
			soup = BeautifulSoup(html, "html.parser")
			title = (soup.title.string or "").strip().lower() if soup.title else ""
			h1 = (soup.find("h1").get_text(strip=True) or "").lower() if soup.find("h1") else ""
			text = (title + " " + h1)
			return (
				"page not found" in text
				or "access denied" in text
				or "forbidden" in text
			)
		except Exception:
			return False

	def crawl(self) -> Tuple[Dict[str, str], Dict[str, str]]:
		"""Return (url->html, url->pdf_relpath) for discovered pages."""
		seen: Set[str] = set()
		html_by_url: Dict[str, str] = {}
		pdf_rel_by_url: Dict[str, str] = {}

		queue: deque[str] = deque([self.start_url])
		headers = {
			"User-Agent": (
				"Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
				"Chrome/124.0.0.0 Safari/537.36"
			),
			"Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
			"Accept-Language": "en-US,en;q=0.9",
		}
		while queue:
			url = queue.popleft()
			if url in seen:
				continue
			if self.max_pages is not None and len(seen) >= self.max_pages:
				break

			try:
				resp = requests.get(url, timeout=30, allow_redirects=True, headers=headers)
				resp.raise_for_status()
				final_url = normalize_url(resp.url, "")
				html = resp.text
			except Exception:
				continue

			# Only accept/record pages that match the allowed prefix (if provided)
			if not self._is_allowed(final_url):
				# Do not mark as seen; skip extracting links from out-of-scope pages
				continue

			# Skip obvious error pages to avoid writing empty PDFs
			if self._looks_like_error_page(html):
				continue

			seen.add(final_url)
			html_by_url[final_url] = html
			pdf_rel_by_url[final_url] = url_to_pdf_relpath(final_url)

			soup = BeautifulSoup(html, "html.parser")
			for a in soup.find_all("a", href=True):
				# Build absolute/normalized link relative to the final URL
				target = normalize_url(final_url, a["href"])
				if self._is_internal(self.start_url, target):
					queue.append(target)

		return html_by_url, pdf_rel_by_url

