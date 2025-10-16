import argparse
import asyncio
import json
import os
from pathlib import Path

from .crawler import collect_internal_urls, render_urls_to_pdf

# Optional: allow selecting Playwright backend via flag


def main() -> None:
    parser = argparse.ArgumentParser(description="Crawl help.sketchup.com/en subtree and export pages to PDF.")
    parser.add_argument(
        "--seed",
        default="https://help.sketchup.com/en/3d-warehouse",
        help="Seed URL to start crawling from (must be under https://help.sketchup.com/en/)",
    )
    parser.add_argument(
        "--allowed-prefix",
        default="https://help.sketchup.com/en/",
        help="Only follow links that start with this prefix.",
    )
    parser.add_argument(
        "--output-root",
        default=str(
            Path("/workspace/pdf_automation/demo_output/help.sketchup.com/en").resolve()
        ),
        help="Output root directory for PDFs (subdirectories mirror site paths).",
    )
    parser.add_argument(
        "--manifest",
        default=str(Path("/workspace/pdf_automation/demo_output/manifest.json").resolve()),
        help="Path to manifest JSON mapping source URLs to generated PDF paths.",
    )
    parser.add_argument(
        "--max-pages",
        type=int,
        default=None,
        help="Optional safety cap to limit number of pages crawled while testing.",
    )
    parser.add_argument(
        "--engine",
        choices=["chrome", "playwright"],
        default="chrome",
        help="Rendering engine: built-in Chrome CLI or Playwright",
    )
    parser.add_argument("--concurrency", type=int, default=4)
    parser.add_argument("--retries", type=int, default=2)
    parser.add_argument("--timeout-ms", type=int, default=90_000)

    args = parser.parse_args()

    if not args.seed.startswith(args.allowed_prefix):
        raise SystemExit(
            f"Seed URL must be under allowed prefix. Got seed={args.seed} allowed_prefix={args.allowed_prefix}"
        )

    os.makedirs(args.output_root, exist_ok=True)
    print(f"Seed: {args.seed}")
    print(f"Allowed prefix: {args.allowed_prefix}")
    urls = collect_internal_urls(
        seed_url=args.seed,
        allowed_prefix=args.allowed_prefix,
        max_pages=args.max_pages,
    )
    print(f"Collected {len(urls)} URL(s) under allowed prefix.")

    if args.engine == "playwright":
        from .playwright_main import render_urls_to_pdf_playwright
        url_to_pdf = asyncio.run(
            render_urls_to_pdf_playwright(
                urls=sorted(urls),
                output_root=args.output_root,
                allowed_prefix=args.allowed_prefix,
                concurrency=args.concurrency,
                retries=args.retries,
                timeout_ms=args.timeout_ms,
            )
        )
    else:
        url_to_pdf = asyncio.run(
            render_urls_to_pdf(
                urls=sorted(urls),
                output_root=args.output_root,
                allowed_prefix=args.allowed_prefix,
            )
        )
    created = sum(1 for _u, p in url_to_pdf.items() if Path(p).exists())
    print(f"Rendered {created} PDF(s) to {args.output_root}")

    # Merge into or create manifest
    manifest_path = Path(args.manifest)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest = {}
    if manifest_path.exists():
        try:
            manifest = json.loads(manifest_path.read_text("utf-8"))
        except Exception:
            manifest = {}
    manifest.update(url_to_pdf)
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Manifest written: {manifest_path}")


if __name__ == "__main__":
    main()

