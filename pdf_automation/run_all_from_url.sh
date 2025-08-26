#!/usr/bin/env bash
set -euo pipefail

# Usage:
#   ./run_all_from_url.sh https://help.sketchup.com/en [OUT_DIR] [MAX_PROCS] [CONCURRENCY] [MAX_DEPTH]
#
# Optional environment variables:
#   DRIVE_SERVICE_ACCOUNT=/abs/path/to/service_account.json
#   DRIVE_FOLDER_ID=<google_drive_folder_id>
#   SAVE_HTML=1  (set to capture HTML alongside PDFs)
#   VERBOSE=1    (set for verbose logs)
#
# Example:
#   ./run_all_from_url.sh https://help.sketchup.com/en /workspace/pdf_automation/pdfs 8 3 3

ROOT_DIR="/workspace/pdf_automation"
URL="${1:-}"
if [[ -z "${URL}" ]]; then
  echo "Usage: $0 https://help.sketchup.com/en [OUT_DIR] [MAX_PROCS] [CONCURRENCY] [MAX_DEPTH]" >&2
  exit 1
fi

OUT_DIR="${2:-${ROOT_DIR}/pdfs}"
MAX_PROCS="${3:-6}"
CONCURRENCY="${4:-3}"
MAX_DEPTH="${5:-3}"

# Ensure dependencies
pip3 install -r "${ROOT_DIR}/requirements.txt"
pip3 install -r "${ROOT_DIR}/pdf_automation/requirements.txt"
python3 -m playwright install --with-deps chromium

EXTRA_ARGS=()

# Optional: Drive upload
if [[ -n "${DRIVE_SERVICE_ACCOUNT:-}" ]]; then
  EXTRA_ARGS+=(--drive-service-account "${DRIVE_SERVICE_ACCOUNT}")
fi
if [[ -n "${DRIVE_FOLDER_ID:-}" ]]; then
  EXTRA_ARGS+=(--drive-folder-id "${DRIVE_FOLDER_ID}")
fi

# Optional flags
if [[ -n "${SAVE_HTML:-}" ]]; then
  EXTRA_ARGS+=(--save-html)
fi
# Always save extracted text to aid debugging/search unless overridden
EXTRA_ARGS+=(--save-text)
if [[ -n "${VERBOSE:-}" ]]; then
  EXTRA_ARGS+=(--verbose)
fi

# Run batch across all discovered sections for the provided URL
python3 -m pdf_automation.batch \
  --url "${URL}" \
  --out "${OUT_DIR}" \
  --crawl-from-main \
  --max-procs "${MAX_PROCS}" \
  --concurrency "${CONCURRENCY}" \
  --max-depth "${MAX_DEPTH}" \
  "${EXTRA_ARGS[@]}"