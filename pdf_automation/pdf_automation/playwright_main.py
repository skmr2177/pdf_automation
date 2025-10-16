import argparse
import asyncio
import json
import logging
from pathlib import Path
from typing import Dict, Iterable, List

from .crawler import collect_internal_urls


async def render_urls_to_pdf_playwright(
    urls: Iterable[str],
    output_root: str,
    allowed_prefix: str,
    *,
    concurrency: int = 4,
    retries: int = 2,
    timeout_ms: int = 90_000,
) -> Dict[str, str]:
    """Render a collection of URLs to PDFs using Playwright (Chromium headless).

    - Only renders URLs that start with the provided allowed_prefix
    - Writes PDFs under output_root, mirroring the site path structure
    - Retries each URL a few times and logs progress
    """
    from playwright.async_api import async_playwright  # lazy import to avoid hard dependency if unused

    log = logging.getLogger("playwright-pdf")
    output_root_path = Path(output_root)
    output_root_path.mkdir(parents=True, exist_ok=True)

    url_to_pdf: Dict[str, str] = {}

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage"]) 
        context = await browser.new_context(
            viewport={"width": 1280, "height": 2000},
            user_agent=(
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
            ),
            locale="en-US",
        )

        semaphore = asyncio.Semaphore(max(1, concurrency))

        async def render_one(url: str) -> None:
            if not url.startswith(allowed_prefix):
                return
            relative = url[len(allowed_prefix):].strip("/")
            safe_relative = (relative or "index").replace("?", "_").replace("&", "_")
            pdf_path = output_root_path / (safe_relative + ".pdf")
            pdf_path.parent.mkdir(parents=True, exist_ok=True)

            attempt = 0
            while attempt <= retries:
                attempt += 1
                async with semaphore:
                    page = await context.new_page()
                    try:
                        log.info("[%s/%s] %s", attempt, retries + 1, url)
                        await page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
                        # Let network settle and wait for common content containers if present
                        try:
                            await page.wait_for_load_state("networkidle", timeout=10_000)
                        except Exception:
                            pass
                        try:
                            await page.wait_for_selector("main, article, #main, .region-content, #content", timeout=5_000)
                        except Exception:
                            pass

                        await page.emulate_media(media="screen")
                        await page.pdf(
                            path=str(pdf_path),
                            format="A4",
                            print_background=True,
                            prefer_css_page_size=True,
                            margin={"top": "12mm", "bottom": "12mm", "left": "12mm", "right": "12mm"},
                        )
                        if pdf_path.exists() and pdf_path.stat().st_size > 0:
                            log.info("Saved %s", pdf_path)
                            break
                        else:
                            log.warning("PDF not created yet for %s (attempt %s)", url, attempt)
                    except Exception as e:
                        log.warning("Render failed for %s (attempt %s): %s", url, attempt, e)
                    finally:
                        try:
                            await page.close()
                        except Exception:
                            pass
            url_to_pdf[url] = str(pdf_path)

        tasks: List[asyncio.Task] = [asyncio.create_task(render_one(u)) for u in sorted(urls)]
        await asyncio.gather(*tasks)

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
    parser.add_argument("--concurrency", type=int, default=4, help="Number of pages to render in parallel")
    parser.add_argument("--retries", type=int, default=2, help="Retries per page if render fails")
    parser.add_argument("--timeout-ms", type=int, default=90_000, help="Navigation timeout per page")

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
            concurrency=args.concurrency,
            retries=args.retries,
            timeout_ms=args.timeout_ms,
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
    created = sum(1 for _u, p in url_to_pdf.items() if Path(p).exists() and Path(p).stat().st_size > 0)
    print(f"Crawled {len(urls)} page(s). Created {created} PDF(s) at: {args.output_root}")
    print(f"Manifest written: {manifest_path}")


if __name__ == "__main__":
    main()

