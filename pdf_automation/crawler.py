import asyncio
import time
from dataclasses import dataclass
from typing import Callable, Optional, Set

from pathlib import Path
from playwright.async_api import async_playwright, Browser

from .cache import Cache
from .render import render_page_to_pdf
from .utils import compute_sha256, is_internal_url, normalize_url, url_to_pdf_path


ALLOWED_HOST = "help.sketchup.com"


@dataclass
class CrawlConfig:
	out_root: Path
	db_path: Path
	concurrency: int = 3
	max_pages: Optional[int] = None
	max_depth: int = 5


class Crawler:
	def __init__(self, config: CrawlConfig) -> None:
		self.config = config
		self.cache = Cache(config.db_path)
		self.seen: Set[str] = set()

	async def _worker(self, browser: Browser, queue: "asyncio.Queue[tuple[str, int]]") -> None:
		while True:
			try:
				url, depth = await queue.get()
			except asyncio.CancelledError:
				return

			if url in self.seen:
				queue.task_done()
				continue
			self.seen.add(url)

			try:
				if depth > self.config.max_depth:
					queue.task_done()
					continue

				if not is_internal_url(url, ALLOWED_HOST):
					queue.task_done()
					continue

				pdf_path = url_to_pdf_path(url, self.config.out_root)

				# Render the page and get original links for recursion
				cleaned_html, links = await render_page_to_pdf(browser, url, pdf_path, self.config.out_root)
				content_hash = compute_sha256(cleaned_html)
				prev = self.cache.get(url)
				if prev and prev.content_hash == content_hash and pdf_path.exists():
					# Already up to date
					queue.task_done()
				else:
					# Update cache
					self.cache.upsert(
						url,
						content_hash=content_hash,
						pdf_path=str(pdf_path),
						last_crawled=int(time.time()),
						status=200,
					)
					# Enqueue internal links
					for link in links:
						if is_internal_url(link, ALLOWED_HOST):
							await queue.put((normalize_url(link), depth + 1))
					queue.task_done()
			except Exception:
				# Best-effort: mark failure
				self.cache.upsert(url, content_hash=None, pdf_path=None, last_crawled=int(time.time()), status=500)
				queue.task_done()

	async def run(self, seeds: list[str]) -> None:
		seeds = [normalize_url(u) for u in seeds]
		async with async_playwright() as p:
			browser = await p.chromium.launch()
			queue: "asyncio.Queue[tuple[str, int]]" = asyncio.Queue()
			for s in seeds:
				await queue.put((s, 0))

			workers = [asyncio.create_task(self._worker(browser, queue)) for _ in range(self.config.concurrency)]
			await queue.join()
			for w in workers:
				w.cancel()
			await browser.close()

