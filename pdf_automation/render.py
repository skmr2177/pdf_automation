import os
import shutil
import subprocess
from bs4 import BeautifulSoup
from urllib.parse import urljoin

from .utils import ensure_parent_directory, normalize_url


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


def rewrite_links_to_local_pdfs(html: str, current_url: str, url_to_pdf_rel: dict[str, str], current_pdf_rel: str) -> str:
	"""Rewrite anchors that point to known URLs to point to local PDF files.

	- Maintains relative layout so that inter-PDF links are navigable locally
	"""
	soup = BeautifulSoup(html, "html.parser")
	for a in soup.find_all("a", href=True):
		raw = a["href"].strip()
		# Resolve and normalize to match manifest keys
		target = normalize_url(current_url, raw)
		# Only rewrite if target matches a known crawled page
		# Keys in url_to_pdf_rel are absolute normalized URLs
		if target in url_to_pdf_rel:
			# Compute a relative path from the current PDF's directory to the target PDF
			current_dir = os.path.dirname(current_pdf_rel)
			rel_target = os.path.relpath(url_to_pdf_rel[target], start=current_dir) if current_dir else url_to_pdf_rel[target]
			a["href"] = rel_target
	return str(soup)


def render_pdf_from_html(html: str, output_file: str, base_url: str | None = None) -> None:
	"""Render HTML to PDF using headless Chrome."""
	ensure_parent_directory(output_file)
	chrome = _find_chrome_binary()
	if not chrome:
		# Fallback: write HTML next to PDF for troubleshooting
		html_path = os.path.splitext(output_file)[0] + ".html"
		with open(html_path, "w", encoding="utf-8") as f:
			f.write(html)
		return

	# Write temp HTML file so Chrome can resolve assets with base URL
	temp_html = os.path.splitext(output_file)[0] + ".__tmp__.html"
	with open(temp_html, "w", encoding="utf-8") as f:
		f.write(html)

	cmd = [
		chrome,
		"--headless=new",
		"--disable-gpu",
		f"--print-to-pdf={os.path.abspath(output_file)}",
		os.path.abspath(temp_html),
	]
	try:
		subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
	finally:
		try:
			os.remove(temp_html)
		except Exception:
			pass

