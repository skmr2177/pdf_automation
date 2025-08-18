import json
import os
from typing import Dict


def load_manifest(manifest_path: str) -> Dict[str, str]:
	"""Load URL->PDF path mapping from disk; return empty mapping if missing."""
	if not os.path.exists(manifest_path):
		return {}
	with open(manifest_path, "r", encoding="utf-8") as f:
		return json.load(f)


def save_manifest(manifest_path: str, mapping: Dict[str, str]) -> None:
	"""Persist URL->PDF path mapping atomically."""
	parent = os.path.dirname(manifest_path)
	if parent and not os.path.exists(parent):
		os.makedirs(parent, exist_ok=True)
	temp_path = manifest_path + ".tmp"
	with open(temp_path, "w", encoding="utf-8") as f:
		json.dump(mapping, f, ensure_ascii=False, indent=2)
	os.replace(temp_path, manifest_path)

