"""Interactive Pokemon data collector.

This script collects raw Pokemon data from PokeAPI and writes JSON files to data/raw.
Supports collection by generation or by game/version.
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

API_BASE = "https://pokeapi.co/api/v2"
OUTPUT_DIR = Path(__file__).resolve().parent
DEFAULT_DELAY_SECONDS = 0.05
MASTER_DATA_FILE = "pokemon_data"
MASTER_DATA_ZH_HANT_FILE = "pokemon_data_zh_hant"
TRADITIONAL_CHINESE = "zh-hant"
STAT_LABELS_ZH_HANT = {
    "hp": "HP",
    "attack": "攻擊",
    "defense": "防禦",
    "special-attack": "特攻",
    "special-defense": "特防",
    "speed": "速度",
}

# Chinese aliases are included because the workflow is used in a Chinese UI.
GAME_QUERY_ALIASES = {
    "朱": "scarlet",
    "紫": "violet",
    "朱紫": "scarlet-violet",
    "sv": "scarlet-violet",
    "scarlet violet": "scarlet-violet",
    "scarlet/violet": "scarlet-violet",
}


def fetch_json(url: str, retries: int = 3, backoff_seconds: float = 1.0) -> dict[str, Any]:
    """Fetch JSON with basic retries for transient network/API errors."""
    last_error: Exception | None = None

    for attempt in range(1, retries + 1):
        try:
            request = Request(
                url,
                headers={
                    "User-Agent": "pokemon-data-collector/1.0 (+https://pokeapi.co/)",
                    "Accept": "application/json",
                },
            )
            with urlopen(request, timeout=30) as response:
                payload = response.read().decode("utf-8")
                return json.loads(payload)
        except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
            last_error = exc
            if isinstance(exc, HTTPError) and exc.code in {400, 404}:
                break
            if attempt == retries:
                break
            sleep_time = backoff_seconds * attempt
            print(f"Request failed ({exc}). Retrying in {sleep_time:.1f}s...")
            time.sleep(sleep_time)

    raise RuntimeError(f"Failed to fetch URL after {retries} attempts: {url}") from last_error


def try_fetch_json(url: str) -> dict[str, Any] | None:
    """Fetch JSON and return None when the resource is missing/unavailable."""
    try:
        return fetch_json(url)
    except RuntimeError:
        return None


def read_json_file(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def extract_id_from_url(url: str) -> int:
    """Extract numeric id from PokeAPI resource URL."""
    return int(url.rstrip("/").split("/")[-1])


def format_pokemon_record(pokemon: dict[str, Any]) -> dict[str, Any]:
    """Keep only fields needed for later processing."""
    return {
        "id": pokemon["id"],
        "name": pokemon["name"],
        "species_name": pokemon["species"]["name"],
        "types": [entry["type"]["name"] for entry in pokemon["types"]],
        "base_stats": {entry["stat"]["name"]: entry["base_stat"] for entry in pokemon["stats"]},
        "abilities": [
            {
                "name": entry["ability"]["name"],
                "is_hidden": entry["is_hidden"],
                "slot": entry["slot"],
            }
            for entry in pokemon["abilities"]
        ],
        "height": pokemon["height"],
        "weight": pokemon["weight"],
    }


def fetch_pokemon_record(pokemon_name: str) -> dict[str, Any]:
    """Fetch a Pokemon record, falling back from species names to default varieties."""
    pokemon_url = f"{API_BASE}/pokemon/{quote(pokemon_name, safe='')}/"
    pokemon_data = try_fetch_json(pokemon_url)
    if pokemon_data is not None:
        return format_pokemon_record(pokemon_data)

    species_url = f"{API_BASE}/pokemon-species/{quote(pokemon_name, safe='')}/"
    species_data = fetch_json(species_url)
    varieties = species_data.get("varieties", [])

    default_variety = next(
        (entry["pokemon"]["name"] for entry in varieties if entry.get("is_default")),
        None,
    )
    if default_variety is None and varieties:
        default_variety = varieties[0]["pokemon"]["name"]
    if default_variety is None:
        raise RuntimeError(f"No varieties found for species: {pokemon_name}")

    fallback_url = f"{API_BASE}/pokemon/{quote(default_variety, safe='')}/"
    pokemon_data = fetch_json(fallback_url)
    return format_pokemon_record(pokemon_data)


def get_localized_name(entries: list[dict[str, Any]], language: str, fallback: str) -> str:
    for entry in entries:
        if entry["language"]["name"] == language:
            return entry["name"]
    return fallback


def fetch_localized_resource_name(resource: str, identifier: str, language: str, fallback: str) -> str:
    data = fetch_json(f"{API_BASE}/{resource}/{quote(identifier, safe='')}/")
    return get_localized_name(data.get("names", []), language, fallback)


def collect_pokemon_records(
    species_refs: list[dict[str, str]],
    delay_seconds: float,
    max_pokemon: int | None,
    label: str,
) -> tuple[list[dict[str, Any]], list[dict[str, str]], int, int]:
    """Collect detailed Pokemon records from species references."""
    species_sorted = sorted(species_refs, key=lambda item: extract_id_from_url(item["url"]))
    available_total = len(species_sorted)

    if max_pokemon is not None:
        species_sorted = species_sorted[:max_pokemon]

    pokemon_records: list[dict[str, Any]] = []
    failures: list[dict[str, str]] = []

    total = len(species_sorted)
    print(f"Collecting {label}: {total} Pokemon")

    for index, species in enumerate(species_sorted, start=1):
        name = species["name"]

        try:
            pokemon_records.append(fetch_pokemon_record(name))
            print(f"[{index}/{total}] OK   {name}")
        except RuntimeError as exc:
            failures.append({"name": name, "error": str(exc)})
            print(f"[{index}/{total}] FAIL {name}")

        if delay_seconds > 0:
            time.sleep(delay_seconds)

    return pokemon_records, failures, total, available_total


def collect_generation(generation: int, delay_seconds: float, max_pokemon: int | None = None) -> dict[str, Any]:
    """Collect Pokemon data for one generation from PokeAPI."""
    generation_url = f"{API_BASE}/generation/{generation}/"
    generation_data = fetch_json(generation_url)

    species_list = generation_data.get("pokemon_species", [])
    pokemon_records, failures, total, available_total = collect_pokemon_records(
        species_refs=species_list,
        delay_seconds=delay_seconds,
        max_pokemon=max_pokemon,
        label=f"generation {generation}",
    )

    collected_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    return {
        "meta": {
            "source": "https://pokeapi.co/",
            "mode": "generation",
            "generation": generation,
            "collected_at_utc": collected_at,
            "available_count": available_total,
            "requested_count": total,
            "success_count": len(pokemon_records),
            "failure_count": len(failures),
            "is_partial": max_pokemon is not None and total < available_total,
        },
        "pokemon": pokemon_records,
        "failures": failures,
    }


def collect_national_dex(delay_seconds: float, max_pokemon: int | None = None) -> dict[str, Any]:
    """Collect a master table in official national PokeAPI order."""
    pokedex_url = f"{API_BASE}/pokedex/national/"
    pokedex_data = fetch_json(pokedex_url)

    entries = sorted(
        pokedex_data.get("pokemon_entries", []),
        key=lambda entry: entry["entry_number"],
    )
    available_total = len(entries)
    if max_pokemon is not None:
        entries = entries[:max_pokemon]

    pokemon_records: list[dict[str, Any]] = []
    failures: list[dict[str, str]] = []
    total = len(entries)

    print(f"Collecting national Pokedex: {total} Pokemon")

    for index, entry in enumerate(entries, start=1):
        species = entry["pokemon_species"]
        species_name = species["name"]

        try:
            record = fetch_pokemon_record(species_name)
            record["dex_number"] = entry["entry_number"]
            pokemon_records.append(record)
            print(f"[{index}/{total}] OK   #{entry['entry_number']} {species_name}")
        except RuntimeError as exc:
            failures.append(
                {
                    "dex_number": str(entry["entry_number"]),
                    "name": species_name,
                    "error": str(exc),
                }
            )
            print(f"[{index}/{total}] FAIL #{entry['entry_number']} {species_name}")

        if delay_seconds > 0:
            time.sleep(delay_seconds)

    collected_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    return {
        "meta": {
            "source": "https://pokeapi.co/",
            "mode": "national-dex",
            "pokedex": "national",
            "collected_at_utc": collected_at,
            "available_count": available_total,
            "requested_count": total,
            "success_count": len(pokemon_records),
            "failure_count": len(failures),
            "is_partial": max_pokemon is not None and total < available_total,
        },
        "pokemon": pokemon_records,
        "failures": failures,
    }


def build_localized_master_table(language: str = TRADITIONAL_CHINESE) -> dict[str, Any]:
    """Build a localized master table from the English national master table."""
    source_path = OUTPUT_DIR / f"{MASTER_DATA_FILE}.json"
    if not source_path.exists():
        raise RuntimeError(f"Missing source file: {source_path}")

    source_payload = read_json_file(source_path)
    source_pokemon = source_payload.get("pokemon", [])
    if not source_pokemon:
        raise RuntimeError(f"Source file has no Pokemon records: {source_path}")

    type_name_map: dict[str, str] = {}
    ability_name_map: dict[str, str] = {}
    species_name_map: dict[str, str] = {}

    unique_types = sorted({type_name for pokemon in source_pokemon for type_name in pokemon["types"]})
    unique_abilities = sorted({ability["name"] for pokemon in source_pokemon for ability in pokemon["abilities"]})
    unique_species = sorted({pokemon["species_name"] for pokemon in source_pokemon})

    print(f"Localizing {len(unique_types)} types...")
    for type_name in unique_types:
        type_name_map[type_name] = fetch_localized_resource_name("type", type_name, language, type_name)

    print(f"Localizing {len(unique_abilities)} abilities...")
    for ability_name in unique_abilities:
        ability_name_map[ability_name] = fetch_localized_resource_name("ability", ability_name, language, ability_name)

    print(f"Localizing {len(unique_species)} Pokemon names...")
    for index, species_name in enumerate(unique_species, start=1):
        species_name_map[species_name] = fetch_localized_resource_name(
            "pokemon-species",
            species_name,
            language,
            species_name,
        )
        print(f"[{index}/{len(unique_species)}] OK   {species_name}")

    localized_pokemon: list[dict[str, Any]] = []
    for pokemon in source_pokemon:
        localized_species_name = species_name_map[pokemon["species_name"]]
        localized_pokemon.append(
            {
                "id": pokemon["id"],
                "dex_number": pokemon["dex_number"],
                "name": localized_species_name,
                "name_en": pokemon["name"],
                "species_name": localized_species_name,
                "species_name_en": pokemon["species_name"],
                "types": [type_name_map[type_name] for type_name in pokemon["types"]],
                "types_en": pokemon["types"],
                "base_stats": {
                    STAT_LABELS_ZH_HANT.get(stat_name, stat_name): stat_value
                    for stat_name, stat_value in pokemon["base_stats"].items()
                },
                "base_stats_en": pokemon["base_stats"],
                "abilities": [
                    {
                        "name": ability_name_map[ability["name"]],
                        "name_en": ability["name"],
                        "is_hidden": ability["is_hidden"],
                        "slot": ability["slot"],
                    }
                    for ability in pokemon["abilities"]
                ],
                "height": pokemon["height"],
                "weight": pokemon["weight"],
            }
        )

    collected_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    return {
        "meta": {
            "source": "https://pokeapi.co/",
            "mode": "national-dex-localized",
            "pokedex": "national",
            "language": language,
            "source_file": source_path.name,
            "source_collected_at_utc": source_payload.get("meta", {}).get("collected_at_utc"),
            "collected_at_utc": collected_at,
            "available_count": len(source_pokemon),
            "requested_count": len(source_pokemon),
            "success_count": len(localized_pokemon),
            "failure_count": 0,
            "is_partial": False,
        },
        "pokemon": localized_pokemon,
        "failures": [],
    }


def normalize_game_query(query: str) -> str:
    """Normalize user input for game/version lookup."""
    normalized = " ".join(query.strip().lower().replace("_", "-").split())
    if normalized in GAME_QUERY_ALIASES:
        return GAME_QUERY_ALIASES[normalized]
    return normalized.replace(" ", "-")


def resolve_version_group(game_query: str) -> dict[str, str]:
    """Resolve user game input to a version-group name."""
    normalized = normalize_game_query(game_query)

    version_data = try_fetch_json(f"{API_BASE}/version/{quote(normalized, safe='')}/")
    if version_data is not None:
        version_group_name = version_data["version_group"]["name"]
        return {
            "input": game_query,
            "normalized_query": normalized,
            "matched_resource": "version",
            "matched_name": version_data["name"],
            "version_group": version_group_name,
        }

    version_group_data = try_fetch_json(f"{API_BASE}/version-group/{quote(normalized, safe='')}/")
    if version_group_data is not None:
        return {
            "input": game_query,
            "normalized_query": normalized,
            "matched_resource": "version-group",
            "matched_name": version_group_data["name"],
            "version_group": version_group_data["name"],
        }

    raise ValueError(
        f"Unknown game/version '{game_query}'. Try values like scarlet, violet, scarlet-violet, 朱紫."
    )


def collect_game(game_query: str, delay_seconds: float, max_pokemon: int | None = None) -> dict[str, Any]:
    """Collect Pokemon data for a game/version by mapping to its version-group pokedex."""
    resolved = resolve_version_group(game_query)
    version_group_name = resolved["version_group"]

    version_group_url = f"{API_BASE}/version-group/{quote(version_group_name, safe='')}/"
    version_group_data = fetch_json(version_group_url)

    pokedexes = version_group_data.get("pokedexes", [])
    if not pokedexes:
        raise RuntimeError(f"No pokedexes found for version-group: {version_group_name}")

    species_by_name: dict[str, dict[str, str]] = {}
    pokedex_names: list[str] = []

    for pokedex_ref in pokedexes:
        pokedex_data = fetch_json(pokedex_ref["url"])
        pokedex_names.append(pokedex_data["name"])
        for entry in pokedex_data.get("pokemon_entries", []):
            species = entry.get("pokemon_species")
            if not species:
                continue
            species_by_name[species["name"]] = species

    species_list = list(species_by_name.values())
    pokemon_records, failures, total, available_total = collect_pokemon_records(
        species_refs=species_list,
        delay_seconds=delay_seconds,
        max_pokemon=max_pokemon,
        label=f"game {version_group_name}",
    )

    collected_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    return {
        "meta": {
            "source": "https://pokeapi.co/",
            "mode": "game",
            "query_input": resolved["input"],
            "normalized_query": resolved["normalized_query"],
            "matched_resource": resolved["matched_resource"],
            "matched_name": resolved["matched_name"],
            "version_group": version_group_name,
            "versions": [item["name"] for item in version_group_data.get("versions", [])],
            "pokedexes": sorted(set(pokedex_names)),
            "collected_at_utc": collected_at,
            "available_count": available_total,
            "requested_count": total,
            "success_count": len(pokemon_records),
            "failure_count": len(failures),
            "is_partial": max_pokemon is not None and total < available_total,
        },
        "pokemon": pokemon_records,
        "failures": failures,
    }


def ensure_output_dir() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def slugify(text: str) -> str:
    """Create a filename-safe slug."""
    safe_chars = []
    for char in text.lower().replace(" ", "-"):
        if char.isalnum() or char in {"-", "_"}:
            safe_chars.append(char)
        else:
            safe_chars.append("-")
    return "".join(safe_chars).strip("-")


def write_output(filename_stem: str, payload: dict[str, Any]) -> Path:
    ensure_output_dir()
    output_path = OUTPUT_DIR / f"{slugify(filename_stem)}.json"
    with output_path.open("w", encoding="utf-8") as file:
        json.dump(payload, file, ensure_ascii=False, indent=2)
    return output_path


def read_positive_int(prompt: str) -> int:
    while True:
        raw = input(prompt).strip()
        if raw.isdigit() and int(raw) > 0:
            return int(raw)
        print("Please enter a positive integer.")


def read_optional_positive_int(prompt: str) -> int | None:
    while True:
        raw = input(prompt).strip()
        if raw == "":
            return None
        if raw.isdigit() and int(raw) > 0:
            return int(raw)
        print("Please enter a positive integer, or press Enter for all.")


def read_delay_seconds() -> float:
    while True:
        raw = input(f"Delay between requests in seconds (default {DEFAULT_DELAY_SECONDS}): ").strip()
        if raw == "":
            return DEFAULT_DELAY_SECONDS

        try:
            value = float(raw)
        except ValueError:
            print("Delay must be a number.")
            continue

        if value < 0:
            print("Delay must be >= 0.")
            continue
        return value


def print_result(output_path: Path, payload: dict[str, Any]) -> None:
    meta = payload["meta"]
    print("\nCollection complete")
    print(f"Saved: {output_path}")
    print(f"Success: {meta['success_count']}  Failures: {meta['failure_count']}")


def run_generation_flow() -> None:
    generation = read_positive_int("Generation number (e.g. 1): ")
    max_pokemon = read_optional_positive_int("Max Pokemon to fetch (Enter for all): ")
    delay_seconds = read_delay_seconds()

    payload = collect_generation(generation, delay_seconds, max_pokemon)
    output_path = write_output(f"generation_{generation}", payload)
    print_result(output_path, payload)


def run_national_dex_flow() -> None:
    max_pokemon = read_optional_positive_int("Max Pokemon to fetch (Enter for all): ")
    delay_seconds = read_delay_seconds()

    payload = collect_national_dex(delay_seconds, max_pokemon)
    output_path = write_output(MASTER_DATA_FILE, payload)
    print_result(output_path, payload)


def run_localized_master_table_flow() -> None:
    payload = build_localized_master_table(TRADITIONAL_CHINESE)
    output_path = write_output(MASTER_DATA_ZH_HANT_FILE, payload)
    print_result(output_path, payload)


def run_game_flow() -> None:
    game_query = input(
        "Game/version (e.g. scarlet, violet, scarlet-violet, 朱紫): "
    ).strip()
    if not game_query:
        print("Game/version cannot be empty.")
        return

    max_pokemon = read_optional_positive_int("Max Pokemon to fetch (Enter for all): ")
    delay_seconds = read_delay_seconds()

    payload = collect_game(game_query, delay_seconds, max_pokemon)
    version_group = payload["meta"]["version_group"]
    output_path = write_output(f"game_{version_group}", payload)
    print_result(output_path, payload)


def main() -> None:
    print("Pokemon Data Collector")
    print("This tool downloads Pokemon data from PokeAPI into the project root.")
    print("1) Collect national master table")
    print("2) Collect by generation")
    print("3) Collect by game/version")
    print("4) Build Traditional Chinese master table from pokemon_data.json")

    choice = input("Choose mode (1, 2, 3, or 4): ").strip()

    try:
        if choice == "1":
            run_national_dex_flow()
        elif choice == "2":
            run_generation_flow()
        elif choice == "3":
            run_game_flow()
        elif choice == "4":
            run_localized_master_table_flow()
        else:
            print("Invalid mode. Please choose 1, 2, 3, or 4.")
    except (RuntimeError, ValueError) as exc:
        print(f"Error: {exc}")


if __name__ == "__main__":
    main()
