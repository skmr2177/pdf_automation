import argparse
import asyncio
from pathlib import Path
from typing import List

from .crawler import Crawler, CrawlConfig


def parse_args() -> argparse.Namespace:
	parser = argparse.ArgumentParser(description="Crawl help.sketchup.com and render pages to PDFs")
	parser.add_argument("--seeds", type=str, nargs="*", help="Seed URLs to start crawling from")
	parser.add_argument("--seeds-file", type=str, help="File containing seed URLs (one per line)", default=None)
	parser.add_argument("--out", type=str, help="Output root directory", default="pdfs")
	parser.add_argument("--db", type=str, help="Path to cache database", default=".cache/crawl.sqlite3")
	parser.add_argument("--concurrency", type=int, default=3)
	parser.add_argument("--max-depth", type=int, default=3)
	parser.add_argument("--allowed-prefix", type=str, nargs="*", default=["/en/"], help="Allowed path prefixes within help.sketchup.com (e.g., /en/ /en/3d-warehouse)")
	return parser.parse_args()


def load_seeds(args: argparse.Namespace) -> List[str]:
	seeds: List[str] = []
	if args.seeds:
		seeds.extend(args.seeds)
	if args.seeds_file:
		p = Path(args.seeds_file)
		if p.exists():
			seeds.extend([line.strip() for line in p.read_text().splitlines() if line.strip() and not line.strip().startswith("#")])
	if not seeds:
		# Use /en as default seed per requirement
		seeds = ["https://help.sketchup.com/en"]
	return seeds


async def amain() -> None:
	args = parse_args()
	out_root = Path(args.out)
	db_path = Path(args.db)
	config = CrawlConfig(out_root=out_root, db_path=db_path, concurrency=args.concurrency, max_depth=args.max_depth, allowed_path_prefixes=args.allowed_prefix)
	crawler = Crawler(config)
	seeds = load_seeds(args)
	await crawler.run(seeds)


def main() -> None:
	asyncio.run(amain())


if __name__ == "__main__":
	main()

