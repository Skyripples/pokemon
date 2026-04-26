from __future__ import annotations

import argparse
import os
from pathlib import Path

from mezastar.module.geocode_stores import (
    DATA_PATH as MEZASTAR_DATA_PATH,
    DEFAULT_DELAY_SECONDS,
    DEFAULT_SAVE_EVERY,
    geocode_stores,
    read_env_value,
)
from mezastar.module.scrape_stores import DEFAULT_PAGE_SIZE, save_json, scrape_all_pages
from mezastar.module.sync_map_config import main as sync_mezastar_map_config


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Pokemon project data update entry.")
    parser.add_argument("--scrape", action="store_true", help="Update Mezastar store data.")
    parser.add_argument("--geocode", action="store_true", help="Fill missing Mezastar lat/lng values.")
    parser.add_argument("--sync-config", action="store_true", help="Write Mezastar map config from .env.")
    parser.add_argument("--data", type=Path, default=MEZASTAR_DATA_PATH, help="Path to Mezastar location JSON.")
    parser.add_argument("--page-size", type=int, default=DEFAULT_PAGE_SIZE, help="Mezastar API page size.")
    parser.add_argument(
        "--api-key",
        default=os.getenv("GOOGLE_MAPS_API_KEY") or read_env_value("GOOGLE_MAPS_API_KEY"),
        help="Google Maps API key. Defaults to GOOGLE_MAPS_API_KEY, then mezastar/setting/.env.",
    )
    parser.add_argument("--delay", type=float, default=DEFAULT_DELAY_SECONDS, help="Delay between geocode requests.")
    parser.add_argument("--limit", type=int, default=None, help="Maximum missing stores to geocode.")
    parser.add_argument("--save-every", type=int, default=DEFAULT_SAVE_EVERY, help="Save geocode progress interval.")
    parser.add_argument("--dry-run", action="store_true", help="List missing geocode targets without API calls.")
    parser.add_argument("--region", default="tw", help="Google geocoding region bias.")
    parser.add_argument("--language", default="zh-TW", help="Google geocoding response language.")
    return parser.parse_args()


def selected_actions(args: argparse.Namespace) -> tuple[bool, bool, bool]:
    has_explicit_action = args.scrape or args.geocode or args.sync_config
    if not has_explicit_action:
        return True, True, True
    return args.scrape, args.geocode, args.sync_config


def main() -> None:
    args = parse_args()
    should_scrape, should_geocode, should_sync_config = selected_actions(args)

    if should_scrape:
        print("[1/3] 更新 Mezastar 店家資料")
        save_json(scrape_all_pages(page_size=args.page_size))

    if should_geocode:
        print("[2/3] 補齊 Mezastar 店家座標")
        geocode_stores(
            path=args.data,
            api_key=args.api_key,
            delay_seconds=args.delay,
            limit=args.limit,
            save_every=args.save_every,
            dry_run=args.dry_run,
            region=args.region,
            language=args.language,
        )

    if should_sync_config:
        print("[3/3] 同步 Mezastar 地圖設定")
        sync_mezastar_map_config()

    print("[DONE] 資料更新流程完成")


if __name__ == "__main__":
    main()
