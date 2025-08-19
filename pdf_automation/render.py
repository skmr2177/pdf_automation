import os
from typing import Dict

from bs4 import BeautifulSoup
from weasyprint import HTML, CSS

from .utils import ensure_parent_directory, compute_file_uri, normalize_url


BASE_CSS = CSS(string="""
/* Typography and layout for clean, page-wise PDFs */
@page {
  size: A4;
  margin: 20mm 18mm 22mm 18mm;
}

html {
  font-size: 12px;
}

body {
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, "Noto Sans", "Apple Color Emoji", "Segoe UI Emoji";
  line-height: 1.55;
  color: #111;
}

h1, h2, h3, h4, h5, h6 {
  font-weight: 700;
  line-height: 1.25;
  margin: 1.2em 0 0.6em;
  page-break-after: avoid;
}

h1 { font-size: 2.0em; border-bottom: 2px solid #e5e7eb; padding-bottom: 0.3em; }
h2 { font-size: 1.6em; border-bottom: 1px solid #e5e7eb; padding-bottom: 0.25em; }
h3 { font-size: 1.3em; }
h4 { font-size: 1.15em; }
h5 { font-size: 1.05em; }
h6 { font-size: 1.0em; color: #374151; }

p, ul, ol, pre, blockquote, table {
  margin: 0.6em 0 0.9em;
}

ul, ol { padding-left: 1.4em; }

code, pre {
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace;
  font-size: 0.95em;
}

pre {
  padding: 0.8em;
  background: #f9fafb;
  border: 1px solid #e5e7eb;
  border-radius: 6px;
  white-space: pre-wrap;
}

a { color: #1d4ed8; text-decoration: none; }
a:hover { text-decoration: underline; }

table {
  border-collapse: collapse;
  width: 100%;
}
th, td {
  border: 1px solid #e5e7eb;
  padding: 6px 8px;
}

/* Avoid bad page breaks */
.avoid-break { page-break-inside: avoid; }
.section { page-break-before: auto; }
""")


def rewrite_links_to_local_pdfs(html_str: str, page_url: str, url_to_pdf_rel: Dict[str, str], current_pdf_relpath: str) -> str:
	"""Rewrite <a href> to point to locally rendered PDFs when available.

	- Given a mapping of canonical URL -> relative PDF path
	- If a link target exists in the mapping, rewrite href to a relative path
	- Otherwise leave as-is
	"""
	soup = BeautifulSoup(html_str, "html.parser")
	for a in soup.find_all("a", href=True):
		href = a["href"]
		canonical = normalize_url(page_url, href)
		if canonical in url_to_pdf_rel:
			target_rel = url_to_pdf_rel[canonical]
			# Compute link path relative to the current PDF's directory
			current_dir = os.path.dirname(current_pdf_relpath)
			relative_href = os.path.relpath(target_rel, start=current_dir or ".")
			a["href"] = relative_href
	return str(soup)


def render_pdf_from_html(html_str: str, output_file: str, base_url: str | None = None) -> None:
	"""Render HTML to a PDF file with the base stylesheet for consistent formatting."""
	ensure_parent_directory(output_file)
	HTML(string=html_str, base_url=base_url).write_pdf(output_file, stylesheets=[BASE_CSS])

