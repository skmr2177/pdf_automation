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

	def __init__(self, start_url: str, same_origin_only: bool = True, max_pages: int | None = None):
		self.start_url = normalize_url(start_url, "")
		self.same_origin_only = same_origin_only
		self.max_pages = max_pages

	def _is_internal(self, base_url: str, target_url: str) -> bool:
		if not self.same_origin_only:
			return True
		from urllib.parse import urlparse
		b = urlparse(base_url)
		t = urlparse(target_url)
		return (b.scheme, b.hostname) == (t.scheme, t.hostname)

	def crawl(self) -> Tuple[Dict[str, str], Dict[str, str]]:
		"""Return (url->html, url->pdf_relpath) for discovered pages."""
		seen: Set[str] = set()
		html_by_url: Dict[str, str] = {}
		pdf_rel_by_url: Dict[str, str] = {}

		queue: deque[str] = deque([self.start_url])
		while queue:
			url = queue.popleft()
			if url in seen:
				continue
			if self.max_pages is not None and len(seen) >= self.max_pages:
				break
			seen.add(url)

			try:
				resp = requests.get(url, timeout=20)
				resp.raise_for_status()
				html = resp.text
			except Exception:
				continue

			html_by_url[url] = html
			pdf_rel_by_url[url] = url_to_pdf_relpath(url)

			soup = BeautifulSoup(html, "html.parser")
			for a in soup.find_all("a", href=True):
				target = normalize_url(url, a["href"])
				if self._is_internal(self.start_url, target):
					queue.append(target)

		return html_by_url, pdf_rel_by_url

