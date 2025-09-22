import os
from collections import deque
from typing import Dict, Iterable, Set, Tuple, Optional

import requests
from bs4 import BeautifulSoup

from .utils import normalize_url, url_to_pdf_relpath


class SiteCrawler:
	"""Breadth-first crawler to collect internal HTML pages.

	Builds a manifest of URL -> relative PDF path locations.
	"""

	def __init__(self, start_url: str, same_origin_only: bool = True, max_pages: int | None = None, allowed_prefix: str | None = None, max_depth: int | None = None):
		self.start_url = normalize_url(start_url, "")
		self.same_origin_only = same_origin_only
		self.max_pages = max_pages
		# If provided, restrict accepted pages to this prefix (after redirects)
		self.allowed_prefix = None if allowed_prefix is None else normalize_url(allowed_prefix, "")
		# Optional maximum crawl depth (0 = only the start URL)
		self.max_depth = max_depth

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
		# Compare host and path to support "/en" and "/en/*" uniformly
		from urllib.parse import urlparse
		ap = urlparse(self.allowed_prefix)
		tp = urlparse(url)
		if (ap.scheme, ap.hostname) != (tp.scheme, tp.hostname):
			return False
		allowed_path = (ap.path or "/").rstrip("/")
		path = tp.path or "/"
		# Allow exact match ("/en") and descendants ("/en/..."), as well as root when allowed_path is "/"
		if allowed_path == "/":
			return True
		return path == allowed_path or path.startswith(allowed_path + "/")

	def crawl(self) -> Tuple[Dict[str, str], Dict[str, str]]:
		"""Return (url->html, url->pdf_relpath) for discovered pages."""
		seen: Set[str] = set()
		queued: Set[str] = set()
		html_by_url: Dict[str, str] = {}
		pdf_rel_by_url: Dict[str, str] = {}

		# BFS queue holds (url, depth)
		queue: deque[Tuple[str, int]] = deque([(self.start_url, 0)])
		queued.add(self.start_url)
		while queue:
			url, depth = queue.popleft()
			if url in seen:
				continue
			if self.max_pages is not None and len(seen) >= self.max_pages:
				break

			try:
				resp = requests.get(url, timeout=20, allow_redirects=True)
				resp.raise_for_status()
			final_url = normalize_url(resp.url, "")
				html = resp.text
			except Exception:
				continue

			# Only accept/record pages that match the allowed prefix (if provided)
			if not self._is_allowed(final_url):
				# Do not mark as seen; skip extracting links from out-of-scope pages
				continue

			seen.add(final_url)
			html_by_url[final_url] = html
			pdf_rel_by_url[final_url] = url_to_pdf_relpath(final_url)

			soup = BeautifulSoup(html, "html.parser")
			# If we've reached max_depth, do not enqueue children
			if self.max_depth is not None and depth >= self.max_depth:
				continue
			for a in soup.find_all("a", href=True):
				# Build absolute/normalized link relative to the final URL
				target = normalize_url(final_url, a["href"])
				if self._is_internal(self.start_url, target) and target not in seen and target not in queued:
					queue.append((target, depth + 1))
					queued.add(target)

		return html_by_url, pdf_rel_by_url

