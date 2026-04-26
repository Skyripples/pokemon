from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable
from urllib.parse import quote

import requests


BASE_URL = "https://www.pokemonmezastar.com.tw"
STORES_URL = f"{BASE_URL}/stores"
API_BASE_URL = "https://api.pokemonmezastar.com.tw/api"
STORE_SEARCH_URL = f"{API_BASE_URL}/v1/store/search"
DEFAULT_PAGE_SIZE = 500

# Keep generated data inside mezastar so GitHub Pages can load it by relative path.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_PATH = PROJECT_ROOT / "data" / "mezastar_locations.json"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36",
    "Accept": "application/json",
    "Content-Type": "application/json",
    "Origin": BASE_URL,
    "Referer": STORES_URL,
}


@dataclass
class StoreItem:
    id: int
    name: str
    address: str
    phone: str
    google_maps_url: str
    tags: list[str]
    source_page: int


def normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def build_google_maps_url(address: str) -> str:
    if not address:
        return ""
    return f"https://www.google.com/maps/search/?api=1&query={quote(address, safe='')}"


def dedupe_stores(items: Iterable[StoreItem]) -> list[StoreItem]:
    seen: set[tuple[int, str, str]] = set()
    result: list[StoreItem] = []

    for item in items:
        key = (item.id, item.name, item.address)
        if key in seen:
            continue
        seen.add(key)
        result.append(item)

    return result


def fetch_store_page(session: requests.Session, page: int, page_size: int) -> tuple[list[StoreItem], int, int]:
    payload = {
        "page": page,
        "page_size": page_size,
    }

    response = session.post(STORE_SEARCH_URL, json=payload, timeout=30)
    response.raise_for_status()

    data = response.json()
    if data.get("code") != 0:
        raise RuntimeError(f"API returned error: {data.get('message', 'Unknown error')}")

    page_data = data.get("data") or {}
    items = page_data.get("items") or []

    stores = [
        StoreItem(
            id=int(item.get("id") or 0),
            name=normalize_text(item.get("name", "")),
            address=normalize_text(item.get("full_address", "")),
            phone=normalize_text(item.get("phone", "")),
            google_maps_url=build_google_maps_url(normalize_text(item.get("full_address", ""))),
            tags=[normalize_text(tag) for tag in item.get("tags") or [] if normalize_text(tag)],
            source_page=page,
        )
        for item in items
        if normalize_text(item.get("name", "")) and normalize_text(item.get("full_address", ""))
    ]

    total_pages = int(page_data.get("total_pages") or 0)
    total_count = int(page_data.get("total_count") or 0)
    return stores, total_pages, total_count


def scrape_all_pages(page_size: int = DEFAULT_PAGE_SIZE) -> list[StoreItem]:
    all_items: list[StoreItem] = []

    with requests.Session() as session:
        session.headers.update(HEADERS)

        current_page = 1
        total_pages = 1
        total_count = 0

        # The API supports a larger page size than the website UI, which keeps updates fast.
        while current_page <= total_pages:
            print(f"[INFO] Fetching page {current_page}/{total_pages}: {STORE_SEARCH_URL}")
            items, total_pages, total_count = fetch_store_page(
                session=session,
                page=current_page,
                page_size=page_size,
            )

            before = len(all_items)
            all_items.extend(items)
            all_items = dedupe_stores(all_items)
            added = len(all_items) - before

            print(
                f"[INFO] Page {current_page}: parsed={len(items)}, added={added}, "
                f"total={len(all_items)}, expected_total={total_count}"
            )
            current_page += 1

    if total_count and len(all_items) != total_count:
        raise RuntimeError(
            f"Fetched store count mismatch: expected {total_count}, got {len(all_items)}"
        )

    return all_items


def load_existing_coordinates(path: Path = OUTPUT_PATH) -> dict[tuple[str, str], dict[str, float]]:
    if not path.exists():
        return {}

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}

    coordinates: dict[tuple[str, str], dict[str, float]] = {}
    for store in payload.get("stores") or []:
        lat = store.get("lat")
        lng = store.get("lng")
        if lat is None or lng is None:
            continue

        address = normalize_text(store.get("address", ""))
        name = normalize_text(store.get("name", ""))
        store_id = str(store.get("id", ""))
        value = {"lat": float(lat), "lng": float(lng)}

        if store_id and address:
            coordinates[(f"id:{store_id}", address)] = value
        if name and address:
            coordinates[(f"name:{name}", address)] = value

    return coordinates


def apply_existing_coordinates(items: list[StoreItem]) -> list[dict[str, object]]:
    existing_coordinates = load_existing_coordinates()
    stores: list[dict[str, object]] = []

    for item in items:
        store = asdict(item)
        coordinate = existing_coordinates.get((f"id:{item.id}", item.address)) or existing_coordinates.get(
            (f"name:{item.name}", item.address)
        )
        if coordinate:
            store.update(coordinate)
        stores.append(store)

    return stores


def save_json(items: list[StoreItem]) -> None:
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)

    stores = apply_existing_coordinates(items)
    payload = {
        "source": STORES_URL,
        "count": len(stores),
        "stores": stores,
    }

    with OUTPUT_PATH.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    print(f"[DONE] Saved to: {OUTPUT_PATH}")


def main() -> None:
    items = scrape_all_pages()
    save_json(items)


if __name__ == "__main__":
    main()
