#!/usr/bin/env python3
"""Report seed vs live catalogs and which API keys are missing.

Prints no secret values. Run from the repo root (uses installed model-radar).

  python scripts/catalog-report.py
  python scripts/catalog-report.py --provider minimax
"""

from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path


def _live_ids(con: sqlite3.Connection, provider: str) -> list[str]:
    return [
        row[0]
        for row in con.execute(
            "SELECT model_id FROM models WHERE provider_key=? AND is_active=1 "
            "ORDER BY model_id",
            (provider,),
        )
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("-p", "--provider", help="Limit to one provider key")
    args = parser.parse_args()

    from model_radar.config import get_api_key, load_config
    from model_radar.db import DB_PATH, catalog_fetched_at, get_cache_meta
    from model_radar.providers import PROVIDERS, SEED_MODELS

    cfg = load_config()
    db_path = Path(DB_PATH)
    con = sqlite3.connect(db_path) if db_path.exists() else None

    print(f"config: {Path.home() / '.model-radar' / 'config.json'}")
    print(f"db:     {db_path} {'(missing)' if con is None else ''}")
    print()

    keys = sorted(PROVIDERS) if not args.provider else [args.provider]
    missing_keys: list[str] = []

    for key in keys:
        prov = PROVIDERS.get(key)
        if not prov:
            print(f"{key}: unknown provider")
            continue
        kind = getattr(prov, "kind", "https")
        seed = [t[0] for t in SEED_MODELS.get(key, prov.models)]
        live = _live_ids(con, key) if con is not None else []
        fetched = catalog_fetched_at(key) if db_path.exists() else None
        source = get_cache_meta(f"catalog:{key}:source") if db_path.exists() else None

        if kind == "cli":
            key_state = "n/a (cli)"
        elif key == "ollama":
            key_state = "local"
        else:
            present = bool(get_api_key(cfg, key))
            key_state = "configured" if present else "MISSING"
            if not present:
                missing_keys.append(key)

        print(f"{key:16} {kind:6} key={key_state:12} seed={len(seed):3} live={len(live):4} "
              f"source={source or '-'} fetched={fetched.isoformat() if fetched else '-'}")
        if live and set(seed) - set(live):
            gone = sorted(set(seed) - set(live))
            print(f"{'':16} seed-not-live ({len(gone)}): {', '.join(gone[:6])}"
                  + ("…" if len(gone) > 6 else ""))
        if live and set(live) - set(seed) and len(live) <= 20:
            extra = sorted(set(live) - set(seed))
            print(f"{'':16} live-not-seed ({len(extra)}): {', '.join(extra[:8])}"
                  + ("…" if len(extra) > 8 else ""))

    if missing_keys:
        print()
        print("Missing API keys:", ", ".join(missing_keys))
        print("  configure_key(provider=…, api_key=…) or model-radar configure <key> <secret>")
        return 1
    print()
    print("All HTTPS providers that need a key have one.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
