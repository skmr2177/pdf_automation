import os
import re
from urllib.parse import urljoin, urlparse, urlunparse


def normalize_url(base_url: str, href: str) -> str:
	"""Return an absolute, normalized URL without fragments.

	- Resolves relative links against base_url
	- Strips URL fragments
	- Normalizes scheme/host casing and removes default ports
	"""
	absolute = urljoin(base_url, href)
	parts = urlparse(absolute)
	# Drop fragment and query for canonicalization during manifest mapping
	parts = parts._replace(fragment="")
	# Keep query only if it seems content-significant; default: drop to dedupe
	parts = parts._replace(query="")
	host = parts.hostname or ""
	# Remove default ports
	port = parts.port
	if (parts.scheme == "http" and port == 80) or (parts.scheme == "https" and port == 443):
		netloc = host
	else:
		netloc = parts.netloc
	canonical = urlunparse((parts.scheme, netloc.lower(), parts.path or "/", parts.params, parts.query, parts.fragment))
	return canonical


def make_file_safe_path(path_component: str) -> str:
	"""Make a string safe for filesystem paths."""
	# Replace unsafe characters with hyphens
	clean = re.sub(r"[^A-Za-z0-9._\-/]", "-", path_component)
	# Collapse repeated separators
	clean = re.sub(r"-+", "-", clean)
	return clean.strip("- ")


def url_to_pdf_relpath(url: str) -> str:
	"""Map a URL to a relative PDF path under the output root.

	Example:
	  https://example.com/a/b -> example.com/a/b.pdf
	  https://example.com/a/   -> example.com/a/index.pdf
	"""
	parts = urlparse(url)
	path = parts.path or "/"
	if path.endswith("/"):
		path = path + "index"
	# If path appears to have an extension, drop it
	if "." in os.path.basename(path):
		stem = os.path.splitext(path)[0]
	else:
		stem = path
	rel = os.path.join(make_file_safe_path(parts.netloc.lower()), make_file_safe_path(stem.lstrip("/"))) + ".pdf"
	return rel


def ensure_parent_directory(file_path: str) -> None:
	"""Create parent directory for a file if missing."""
	parent = os.path.dirname(file_path)
	if parent and not os.path.exists(parent):
		os.makedirs(parent, exist_ok=True)


def compute_file_uri(absolute_path: str) -> str:
	"""Return a file:// URI for a local absolute path."""
	return f"file://{os.path.abspath(absolute_path)}"

