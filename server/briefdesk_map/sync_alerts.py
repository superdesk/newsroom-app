#!/usr/bin/env python3
"""Copy the demo seed script's geo index into this package.

The Superdesk side of the demo writes
`superdesk/server/scripts/demo/content/geo_index.json`, a list of
`{reference, title, severity, lat, lon, country, region, sector}` entries for
the sample alerts it seeds. Copying it here makes the map show the same alerts
that are in the Intelligence Feed, so the "Open in Intelligence Feed" links
resolve.

Usage:

    python3 server/briefdesk_map/sync_alerts.py [SOURCE]
    python3 server/briefdesk_map/sync_alerts.py --clear

Without SOURCE the script looks for the geo index next to this checkout. The
copy lands in `data/geo_index.json`, which the module prefers over its own
`data/alerts.json` fallback. `--clear` removes the copy and goes back to the
fallback.
"""

import argparse
import json
import pathlib
import sys

PACKAGE_DIR = pathlib.Path(__file__).resolve().parent
TARGET = PACKAGE_DIR / "data" / "geo_index.json"

REQUIRED_FIELDS = ("reference", "title", "severity", "lat", "lon", "region", "sector")

#: Where the Superdesk distribution sits relative to this worktree in the demo layout.
DEFAULT_SOURCES = [
    PACKAGE_DIR.parents[2] / "superdesk" / "server" / "scripts" / "demo" / "content" / "geo_index.json",
    PACKAGE_DIR.parents[3] / "superdesk" / "server" / "scripts" / "demo" / "content" / "geo_index.json",
]


def find_source(explicit):
    if explicit:
        return pathlib.Path(explicit).expanduser().resolve()
    for candidate in DEFAULT_SOURCES:
        if candidate.exists():
            return candidate
    return None


def validate(alerts):
    if not isinstance(alerts, list) or not alerts:
        raise ValueError("geo index must be a non-empty list")

    for index, alert in enumerate(alerts):
        if not isinstance(alert, dict):
            raise ValueError(f"entry {index} is not an object")
        missing = [field for field in REQUIRED_FIELDS if field not in alert]
        if missing:
            raise ValueError(f"entry {index} ({alert.get('reference')}) is missing {', '.join(missing)}")
        float(alert["lat"])
        float(alert["lon"])


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("source", nargs="?", help="path to geo_index.json")
    parser.add_argument("--clear", action="store_true", help="remove the synced copy and use the fallback")
    args = parser.parse_args()

    if args.clear:
        if TARGET.exists():
            TARGET.unlink()
            print(f"removed {TARGET}")
        else:
            print("nothing to remove")
        return 0

    source = find_source(args.source)
    if source is None or not source.exists():
        print("geo index not found, the map keeps using its own alerts.json", file=sys.stderr)
        if source is not None:
            print(f"looked for {source}", file=sys.stderr)
        return 1

    with open(source, "r", encoding="utf-8") as handle:
        alerts = json.load(handle)

    validate(alerts)

    with open(TARGET, "w", encoding="utf-8") as handle:
        json.dump(alerts, handle, ensure_ascii=False, indent=2)
        handle.write("\n")

    print(f"copied {len(alerts)} alerts from {source} to {TARGET}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
