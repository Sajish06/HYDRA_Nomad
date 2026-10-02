"""Check connectivity, health, and scopes on local Meetily Pro gateway."""

import asyncio
import sys
from pathlib import Path

# Ensure repository root is on sys.path
root_dir = Path(__file__).resolve().parent.parent
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

from backend.config import settings
from backend.meetily.client import MeetilyClient
from backend.meetily.errors import MeetilyAuthError, MeetilyConnectionError


async def main():
    print("=" * 60)
    print("Meetily Pro Gateway Connection Check")
    print(f"Target URL: {settings.MEETILY_BASE_URL}")
    print("=" * 60)

    client = MeetilyClient()

    # 1. Health check
    try:
        health = await client.health()
        print(f"[OK] Health endpoint reachable: {health}")
    except MeetilyConnectionError as e:
        print(f"[FAIL] Could not connect to Meetily at {settings.MEETILY_BASE_URL}.")
        print("Ensure Meetily Pro 1.11.0+ is running with Automation API enabled in settings.")
        print(f"Details: {e.details}")
        sys.exit(1)
    except Exception as e:
        print(f"[WARN] Health endpoint returned: {e}")

    # 2. Token & Whoami check
    if not settings.MEETILY_API_TOKEN:
        print("[INFO] No MEETILY_API_TOKEN provided in environment. Read-only loopback access may apply.")
    else:
        try:
            whoami = await client.whoami()
            print(f"[OK] Authentication valid. Identity: {whoami}")
        except MeetilyAuthError as e:
            print(f"[FAIL] Authentication failed (HTTP {e.status_code}). Check your MEETILY_API_TOKEN.")
            sys.exit(1)
        except Exception as e:
            print(f"[INFO] WhoAmI endpoint returned: {e}")

    # 3. OpenAPI check
    try:
        spec = await client.openapi()
        title = spec.get("info", {}).get("title", "Meetily API")
        version = spec.get("info", {}).get("version", "unknown")
        print(f"[OK] OpenAPI schema retrieved: {title} v{version}")
    except Exception as e:
        print(f"[WARN] OpenAPI schema not reachable: {e}")

    print("=" * 60)
    print("All checks completed.")


if __name__ == "__main__":
    asyncio.run(main())
