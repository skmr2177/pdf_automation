#!/usr/bin/env python3
import argparse
import os
import subprocess
import sys
from pathlib import Path
from typing import List


def install_dependencies(root_dir: Path, *, verbose: bool = False) -> None:
    reqs: List[Path] = [
        root_dir / "requirements.txt",
        root_dir / "pdf_automation" / "requirements.txt",
    ]

    for req in reqs:
        if req.exists():
            cmd = [sys.executable, "-m", "pip", "install", "-r", str(req)]
            if verbose:
                print("[deps] ", " ".join(cmd))
            subprocess.run(cmd, check=True)

    # Playwright runtime/browsers
    cmd = [sys.executable, "-m", "playwright", "install", "--with-deps", "chromium"]
    if verbose:
        print("[deps] ", " ".join(cmd))
    subprocess.run(cmd, check=True)


def build_command(
    url: str,
    out_dir: Path,
    *,
    max_procs: int,
    concurrency: int,
    max_depth: int,
    save_html: bool,
    save_text: bool,
    verbose: bool,
    drive_service_account: str | None,
    drive_folder_id: str | None,
) -> List[str]:
    cmd: List[str] = [
        sys.executable,
        "-m",
        "pdf_automation.batch",
        "--url",
        url,
        "--out",
        str(out_dir),
        "--crawl-from-main",
        "--max-procs",
        str(max_procs),
        "--concurrency",
        str(concurrency),
        "--max-depth",
        str(max_depth),
    ]

    if save_html:
        cmd.append("--save-html")
    if save_text:
        cmd.append("--save-text")
    if verbose:
        cmd.append("--verbose")
    if drive_service_account:
        cmd.extend(["--drive-service-account", drive_service_account])
    if drive_folder_id:
        cmd.extend(["--drive-folder-id", drive_folder_id])

    return cmd


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run all discovered help.sketchup.com categories in parallel from a URL",
    )
    parser.add_argument("url", help="help.sketchup.com URL (e.g. https://help.sketchup.com/en)")
    parser.add_argument(
        "--out",
        type=str,
        default=None,
        help="Output root directory (default: <repo>/pdfs)",
    )
    parser.add_argument("--max-procs", type=int, default=6, help="Max parallel section processes")
    parser.add_argument("--concurrency", type=int, default=3, help="Per-process crawler workers")
    parser.add_argument("--max-depth", type=int, default=3, help="Crawl depth from section main page")
    parser.add_argument("--save-html", action="store_true", help="Save captured HTML alongside PDFs")
    parser.add_argument(
        "--save-text",
        action="store_true",
        help="Save extracted text alongside PDFs (recommended)",
    )
    parser.add_argument("--verbose", action="store_true", help="Verbose logs")

    # Dependency setup
    parser.add_argument(
        "--install-deps",
        action="store_true",
        help="Install Python deps and Playwright browsers before running",
    )

    # Drive upload options (env vars are also respected)
    parser.add_argument(
        "--drive-service-account",
        type=str,
        default=None,
        help="Path to Google service account JSON for Drive uploads (or env DRIVE_SERVICE_ACCOUNT)",
    )
    parser.add_argument(
        "--drive-folder-id",
        type=str,
        default=None,
        help="Google Drive folder ID (or env DRIVE_FOLDER_ID)",
    )

    return parser.parse_args()


def main() -> int:
    args = parse_args()

    root_dir = Path(__file__).resolve().parent
    out_dir = Path(args.out) if args.out else (root_dir / "pdfs")
    out_dir.mkdir(parents=True, exist_ok=True)

    if args.install_deps:
        install_dependencies(root_dir, verbose=args.verbose)

    # Allow env var overrides
    drive_service_account = (
        args.drive_service_account or os.environ.get("DRIVE_SERVICE_ACCOUNT")
    )
    drive_folder_id = args.drive_folder_id or os.environ.get("DRIVE_FOLDER_ID")

    cmd = build_command(
        url=args.url,
        out_dir=out_dir,
        max_procs=args.max_procs,
        concurrency=args.concurrency,
        max_depth=args.max_depth,
        save_html=args.save_html,
        save_text=(True if args.save_text else True),  # default to saving text
        verbose=args.verbose,
        drive_service_account=drive_service_account,
        drive_folder_id=drive_folder_id,
    )

    if args.verbose:
        print("[run] ", " ".join(cmd))

    proc = subprocess.run(cmd)
    return proc.returncode


if __name__ == "__main__":
    raise SystemExit(main())