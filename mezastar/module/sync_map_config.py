from __future__ import annotations

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
ENV_PATH = PROJECT_ROOT / "setting" / ".env"
OUTPUT_PATH = PROJECT_ROOT / "config.js"


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


def main() -> None:
    api_key = read_env_value("GOOGLE_MAPS_API_KEY")
    if not api_key or api_key == "YOUR_GOOGLE_MAPS_API_KEY":
        raise RuntimeError("Missing GOOGLE_MAPS_API_KEY in .env")

    OUTPUT_PATH.write_text(
        '\n'.join(
            [
                "window.MEZASTAR_MAP_CONFIG = {",
                f'  googleMapsApiKey: "{api_key}"',
                "};",
                "",
            ]
        ),
        encoding="utf-8",
    )
    print(f"[DONE] Wrote {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
