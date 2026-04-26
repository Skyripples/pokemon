from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import time
from pathlib import Path
from typing import Any

import requests


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_PATH = PROJECT_ROOT / "data" / "mezastar_locations.json"
ENV_PATH = PROJECT_ROOT / "setting" / ".env"
GOOGLE_GEOCODE_URL = "https://maps.googleapis.com/maps/api/geocode/json"
DEFAULT_DELAY_SECONDS = 0.15
DEFAULT_SAVE_EVERY = 10


def load_payload(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def save_payload(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def has_coordinates(store: dict[str, Any]) -> bool:
    return store.get("lat") is not None and store.get("lng") is not None


def normalize_address(address: str) -> str:
    return re.sub(r"\s+", " ", address or "").strip()


def read_env_value(name: str, path: Path = ENV_PATH) -> str:
    if not path.exists():
        return ""

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        if key.strip() != name:
            continue
        return value.strip().strip('"').strip("'")
    return ""


def geocode_address(
    session: requests.Session,
    api_key: str,
    address: str,
    region: str,
    language: str,
) -> tuple[float, float]:
    response = session.get(
        GOOGLE_GEOCODE_URL,
        params={
            "address": address,
            "key": api_key,
            "region": region,
            "language": language,
        },
        timeout=30,
    )
    response.raise_for_status()

    data = response.json()
    status = data.get("status")
    if status != "OK":
        message = data.get("error_message") or status or "Unknown geocoding error"
        raise RuntimeError(message)

    results = data.get("results") or []
    if not results:
        raise RuntimeError("No geocoding result")

    location = results[0]["geometry"]["location"]
    return float(location["lat"]), float(location["lng"])


def geocode_stores(
    path: Path,
    api_key: str,
    delay_seconds: float,
    limit: int | None,
    save_every: int,
    dry_run: bool,
    region: str,
    language: str,
) -> None:
    payload = load_payload(path)
    stores = payload.get("stores") or []
    missing = [store for store in stores if not has_coordinates(store)]

    print(f"[INFO] Data file: {path}")
    print(f"[INFO] Store count: {len(stores)}")
    print(f"[INFO] Missing coordinates: {len(missing)}")

    if not missing:
        print("[DONE] All stores already have coordinates.")
        return

    if dry_run:
        for store in missing[: limit or 10]:
            print(f"[DRY] {store.get('id')} {store.get('name')} | {store.get('address')}")
        return

    if not api_key:
        raise RuntimeError("Missing API key. Set GOOGLE_MAPS_API_KEY or pass --api-key.")

    backup_path = path.with_suffix(path.suffix + ".bak")
    if not backup_path.exists():
        shutil.copy2(path, backup_path)
        print(f"[INFO] Backup created: {backup_path}")

    processed = 0
    success = 0
    failed = 0

    with requests.Session() as session:
        for store in missing:
            if limit is not None and processed >= limit:
                break

            processed += 1
            address = normalize_address(store.get("address", ""))
            if not address:
                failed += 1
                print(f"[WARN] Missing address: {store.get('id')} {store.get('name')}")
                continue

            try:
                lat, lng = geocode_address(
                    session=session,
                    api_key=api_key,
                    address=address,
                    region=region,
                    language=language,
                )
                store["lat"] = lat
                store["lng"] = lng
                success += 1
                print(f"[OK] {success}/{processed} {store.get('name')} -> {lat}, {lng}")
            except Exception as error:
                failed += 1
                print(f"[WARN] {store.get('id')} {store.get('name')} failed: {error}")

            if processed % save_every == 0:
                save_payload(path, payload)
                print(f"[INFO] Progress saved after {processed} processed")

            if delay_seconds > 0:
                time.sleep(delay_seconds)

    save_payload(path, payload)

    remaining = sum(1 for store in stores if not has_coordinates(store))
    print(f"[DONE] Processed: {processed}, success: {success}, failed: {failed}")
    print(f"[DONE] Remaining missing coordinates: {remaining}")
    print(f"[DONE] Saved: {path}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Add lat/lng coordinates to Mezastar store JSON.")
    parser.add_argument("--data", type=Path, default=DATA_PATH, help="Path to mezastar_locations.json.")
    parser.add_argument(
        "--api-key",
        default=os.getenv("GOOGLE_MAPS_API_KEY") or read_env_value("GOOGLE_MAPS_API_KEY"),
        help="Google Maps API key. Defaults to GOOGLE_MAPS_API_KEY, then mezastar/setting/.env.",
    )
    parser.add_argument("--delay", type=float, default=DEFAULT_DELAY_SECONDS, help="Delay between requests.")
    parser.add_argument("--limit", type=int, default=None, help="Maximum missing stores to geocode.")
    parser.add_argument("--save-every", type=int, default=DEFAULT_SAVE_EVERY, help="Save after this many requests.")
    parser.add_argument("--dry-run", action="store_true", help="List missing stores without calling Google.")
    parser.add_argument("--region", default="tw", help="Geocoding region bias.")
    parser.add_argument("--language", default="zh-TW", help="Geocoding response language.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
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


if __name__ == "__main__":
    main()
