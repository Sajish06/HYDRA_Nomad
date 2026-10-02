"""Fetch the live OpenAPI schema from Meetily gateway and validate adapter assumptions."""

import asyncio
import json
import sys
from pathlib import Path

# Ensure repository root is on sys.path
root_dir = Path(__file__).resolve().parent.parent
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

from backend.meetily.client import MeetilyClient

SNAPSHOT_PATH = Path("docs/openapi.snapshot.json")


def validate_against_schema(spec: dict) -> dict:
    """Check how well our schema adapter contracts match the discovered OpenAPI schema."""
    paths = spec.get("paths", {})
    results = {
        "has_health": "/health" in paths,
        "has_whoami": "/v1/whoami" in paths or "/whoami" in paths,
        "has_meetings": "/v1/meetings" in paths or "/meetings" in paths,
        "has_transcript": any("/transcript" in p for p in paths),
        "has_summary": any("/summary" in p for p in paths),
    }
    return results


async def main():
    print("Connecting to Meetily gateway to fetch OpenAPI specification...")
    client = MeetilyClient()
    try:
        spec = await client.openapi()
        SNAPSHOT_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(SNAPSHOT_PATH, "w", encoding="utf-8") as f:
            json.dump(spec, f, indent=2)
        print(f"[OK] Saved live OpenAPI schema snapshot to {SNAPSHOT_PATH}")

        # Run contract check
        results = validate_against_schema(spec)
        print("\nContract Check Results against Live Gateway:")
        for check, passed in results.items():
            status = "[PASS]" if passed else "[WARN]"
            print(f"  {status} {check}")

    except Exception as e:
        print(f"[ERROR] Failed to fetch OpenAPI specification: {e}")
        print("Ensure Meetily is running on http://127.0.0.1:8420 with Automation API enabled.")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
