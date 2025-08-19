import argparse
import asyncio
import json
from pathlib import Path
from typing import Dict, Iterable

from .crawler import collect_internal_urls


async def render_urls_to_pdf_playwright(urls: Iterable[str], output_root: str, allowed_prefix: str) -> Dict[str, str]:
    """Render a collection of URLs to PDFs using Playwright (Chromium headless).

    - Only renders URLs that start with the provided allowed_prefix
    - Writes PDFs under output_root, mirroring the site path structure
    """
    from playwright.async_api import async_playwright  # lazy import to avoid hard dependency if unused

    output_root_path = Path(output_root)
    output_root_path.mkdir(parents=True, exist_ok=True)

    url_to_pdf: Dict[str, str] = {}

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        for url in sorted(urls):
            if not url.startswith(allowed_prefix):
                continue
            relative = url[len(allowed_prefix):].strip("/")
            safe_relative = (relative or "index").replace("?", "_").replace("&", "_")
            pdf_path = output_root_path / (safe_relative + ".pdf")
            pdf_path.parent.mkdir(parents=True, exist_ok=True)

            page = await context.new_page()
            try:
                await page.goto(url, wait_until="networkidle", timeout=90_000)
                await page.emulate_media(media="screen")
                await page.pdf(
                    path=str(pdf_path),
                    format="A4",
                    print_background=True,
                    margin={"top": "12mm", "bottom": "12mm", "left": "12mm", "right": "12mm"},
                )
            except Exception:
                # Swallow errors to continue rendering the rest
                pass
            finally:
                try:
                    await page.close()
                except Exception:
                    pass

            url_to_pdf[url] = str(pdf_path)

        await context.close()
        await browser.close()

    return url_to_pdf


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Crawl help.sketchup.com/en subtree and export pages to PDF using Playwright (Chromium).",
    )
    parser.add_argument(
        "--seed",
        default="https://help.sketchup.com/en/3d-warehouse",
        help="Seed URL to start crawling from (must be under https://help.sketchup.com/en/)",
    )
    parser.add_argument(
        "--allowed-prefix",
        default="https://help.sketchup.com/en/",
        help="Only follow and render links that start with this prefix.",
    )
    parser.add_argument(
        "--out",
        dest="output_root",
        default=str(Path("/workspace/pdf_automation/demo_output/help.sketchup.com/en").resolve()),
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

    args = parser.parse_args()

    if not args.seed.startswith(args.allowed_prefix):
        raise SystemExit(
            f"Seed URL must be under allowed prefix. Got seed={args.seed} allowed_prefix={args.allowed_prefix}"
        )

    urls = collect_internal_urls(
        seed_url=args.seed,
        allowed_prefix=args.allowed_prefix,
        max_pages=args.max_pages,
    )

    url_to_pdf = asyncio.run(
        render_urls_to_pdf_playwright(
            urls=urls,
            output_root=args.output_root,
            allowed_prefix=args.allowed_prefix,
        )
    )

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
    print(f"Crawled {len(urls)} page(s). PDFs written to: {args.output_root}")
    print(f"Manifest written: {manifest_path}")


if __name__ == "__main__":
    main()

