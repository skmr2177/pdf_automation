import argparse
import os
from typing import Dict

from .cache import load_manifest, save_manifest
from .crawler import SiteCrawler
from .render import render_pdf_from_html, rewrite_links_to_local_pdfs
from .utils import compute_file_uri


def build(start_url: str, output_root: str, same_origin_only: bool = True, max_pages: int | None = None, allowed_prefix: str | None = None) -> None:
	"""Crawl, rewrite links to local PDFs, and render each page to a PDF."""
	manifest_path = os.path.join(output_root, "manifest.json")
	os.makedirs(output_root, exist_ok=True)

	# Crawl
	crawler = SiteCrawler(start_url=start_url, same_origin_only=same_origin_only, max_pages=max_pages, allowed_prefix=allowed_prefix)
	html_by_url, url_to_pdf_rel = crawler.crawl()

	# Persist manifest for re-use
	save_manifest(manifest_path, url_to_pdf_rel)

	# Render each page, rewriting internal links to local PDFs
	for url, html in html_by_url.items():
		current_rel = url_to_pdf_rel[url]
		rewritten = rewrite_links_to_local_pdfs(html, url, url_to_pdf_rel, current_rel)
		output_file = os.path.join(output_root, current_rel)
		# Base URL ensures relative assets resolve correctly during render
		render_pdf_from_html(rewritten, output_file=output_file, base_url=os.path.dirname(output_file))


def main() -> None:
	parser = argparse.ArgumentParser(description="Crawl a site and render each page to a PDF with local link rewriting.")
	parser.add_argument("start_url", help="Starting URL to crawl")
	parser.add_argument("--out", dest="output_root", default="out", help="Output directory root (default: out)")
	parser.add_argument("--all-origins", dest="same_origin_only", action="store_false", help="Allow off-origin links (default: same-origin only)")
	parser.add_argument("--max-pages", dest="max_pages", type=int, default=None, help="Limit number of pages to crawl")
	parser.add_argument("--allowed-prefix", dest="allowed_prefix", default=None, help="Only include pages whose final URL starts with this prefix")
	args = parser.parse_args()

	build(start_url=args.start_url, output_root=args.output_root, same_origin_only=args.same_origin_only, max_pages=args.max_pages, allowed_prefix=args.allowed_prefix)


if __name__ == "__main__":
	main()

