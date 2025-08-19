import asyncio
from pathlib import Path
from typing import Optional

from bs4 import BeautifulSoup
from playwright.async_api import Browser, Page

from .utils import clean_main_content, is_internal_url, make_relative_href, url_to_pdf_path, extract_links


PRINT_CSS = """
@page { size: A4; margin: 18mm 15mm 20mm 15mm; }
html, body { font: 12px/1.55 system-ui, -apple-system, Segoe UI, Roboto, Arial, sans-serif; color: #111; }
main, article { max-width: 800px; margin: 0 auto; }
h1 { font-size: 22px; margin: 0 0 10px; }
h2 { font-size: 18px; margin: 18px 0 8px; }
h3 { font-size: 16px; margin: 14px 0 6px; }
h1, h2, h3 { page-break-after: avoid; break-after: avoid; }
h2 + p, h3 + p, h2 + ul, h3 + ul { page-break-before: avoid; }
p, ul, ol, blockquote { orphans: 3; widows: 3; }
ul, ol { margin: 0 0 10px 20px; }
li { page-break-inside: avoid; }
img, svg { max-width: 100%; height: auto; page-break-inside: avoid; }
table { width: 100%; border-collapse: collapse; page-break-inside: avoid; }
th, td { border: 1px solid #ddd; padding: 6px 8px; }
thead { display: table-header-group; }
pre, code, kbd { font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; }
pre { background: #f6f8fa; border: 1px solid #e2e6ea; border-radius: 4px; padding: 10px 12px; margin: 12px 0; white-space: pre-wrap; word-break: break-word; tab-size: 2; page-break-inside: avoid; overflow: visible; }
code { background: #f6f8fa; padding: 0 3px; border-radius: 3px; }
a { color: #0b63ce; text-decoration: none; }
a[href] { text-decoration: underline; }
a:visited { color: #6b4fb3; }
header, nav, footer, .toc, .cookie, .banner, .ads, .share, .breadcrumbs, .feedback { display: none !important; }
"""


async def inject_content_and_rewrite_links(page: Page, base_url: str, out_root: Path, current_pdf_path: Path) -> str:
	full_html = await page.content()
	cleaned_html = clean_main_content(full_html)

	soup = BeautifulSoup(cleaned_html, "lxml")
	for a in soup.find_all("a", href=True):
		href = a.get("href")
		# Leave relative links for Playwright to resolve; we will rewrite by computing absolute and mapping to PDF
		# Convert external links to plain text
		from urllib.parse import urljoin, urlparse
		abs_href = urljoin(base_url, href)
		if urlparse(abs_href).netloc and urlparse(abs_href).netloc != "help.sketchup.com":
			a.name = "span"
			if "href" in a.attrs:
				del a["href"]
			continue
		# Internal link: rewrite to target pdf relative path
		if abs_href and (urlparse(abs_href).netloc == "help.sketchup.com"):
			target_pdf = url_to_pdf_path(abs_href, out_root)
			a["href"] = make_relative_href(current_pdf_path, target_pdf)

	html_str = str(soup)
	await page.set_content(html_str, wait_until="load")
	await page.add_style_tag(content=PRINT_CSS)
	await page.emulate_media(media="print")
	return html_str


async def render_page_to_pdf(browser: Browser, url: str, pdf_path: Path, out_root: Path) -> tuple[str, list[str]]:
	pdf_path.parent.mkdir(parents=True, exist_ok=True)
	page = await browser.new_page()

	# Block analytics to speed up
	async def route_block(route):
		req = route.request
		if any(k in req.url for k in ["/analytics", "google-analytics", "gtag", "segment", "optimizely", "/collect?"]):
			return await route.abort()
		return await route.continue_()

	await page.route("**/*", route_block)
	await page.goto(url, wait_until="networkidle")

	# Extract links for crawling BEFORE we rewrite anchors to local PDF paths
	original_html = await page.content()
	links_for_crawl = extract_links(original_html, url)

	cleaned_html = await inject_content_and_rewrite_links(page, url, out_root, pdf_path)

	header_template = """
	  <style>section{font-size:10px;width:100%;padding:0 10px;color:#666;font-family:Arial, sans-serif}</style>
	  <section><span class="title"></span></section>
	"""
	footer_template = """
	  <style>section{font-size:10px;width:100%;padding:0 10px;color:#666;font-family:Arial, sans-serif}</style>
	  <section>
		<span class="url"></span>
		<div style="float:right">Page <span class="pageNumber"></span> of <span class="totalPages"></span></div>
	  </section>
	"""

	await page.pdf(
		path=str(pdf_path),
		format="A4",
		print_background=True,
		margin={"top": "18mm", "right": "15mm", "bottom": "20mm", "left": "15mm"},
		display_header_footer=True,
		header_template=header_template,
		footer_template=footer_template,
	)
	await page.close()
	return cleaned_html, links_for_crawl