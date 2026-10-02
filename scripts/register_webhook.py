"""Register Clean Room webhook endpoint with running Meetily Pro instance."""

import asyncio
import sys
from pathlib import Path

import httpx

# Ensure repository root is on sys.path
root_dir = Path(__file__).resolve().parent.parent
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

from backend.config import settings


async def main():
    print("=" * 65)
    print("Meetily Pro Webhook Registration")
    print("=" * 65)

    if not settings.WEBHOOK_PUBLIC_URL:
        print("[ERROR] WEBHOOK_PUBLIC_URL is not set.")
        print("Please configure a reachable callback URL (e.g. via ngrok/localtunnel):")
        print("Example: WEBHOOK_PUBLIC_URL=https://your-tunnel.ngrok-free.app/api/webhooks/meetily")
        sys.exit(1)

    url = f"{settings.MEETILY_BASE_URL.rstrip('/')}/v1/webhooks"
    headers = {"Content-Type": "application/json"}
    if settings.MEETILY_API_TOKEN:
        headers["Authorization"] = f"Bearer {settings.MEETILY_API_TOKEN.get_secret_value()}"

    payload = {
        "event_type": "summary.completed",
        "url": settings.WEBHOOK_PUBLIC_URL,
        "description": "Meetily Clean Room verification and masking gatekeeper",
    }

    print(f"Target Gateway: {settings.MEETILY_BASE_URL}")
    print(f"Callback URL:   {settings.WEBHOOK_PUBLIC_URL}")
    print("Subscribing to: summary.completed\n")

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(url, headers=headers, json=payload)

            if resp.status_code in (200, 201):
                data = resp.json()
                webhook_id = data.get("id") or data.get("webhook_id") or "wh_registered"
                one_time_secret = data.get("secret") or data.get("signing_secret")

                print(f"[SUCCESS] Webhook registered successfully! ID: {webhook_id}")
                if one_time_secret:
                    print("\n" + "!" * 65)
                    print("IMPORTANT: Store this one-time HMAC signing secret in your .env:")
                    print(f"WEBHOOK_SECRET={one_time_secret}")
                    print("This secret will NOT be shown again. Never commit it to git.")
                    print("!" * 65 + "\n")
                else:
                    print("[INFO] No signing secret returned. Use your configured secret.")

                print("Note: The destination may show as pending until approved in Meetily settings.")
            else:
                print(f"[FAIL] Registration failed with HTTP {resp.status_code}: {resp.text}")
                sys.exit(1)

    except httpx.ConnectError:
        print(f"[FAIL] Could not connect to Meetily at {settings.MEETILY_BASE_URL}.")
        print("Ensure Meetily Pro is running and Automation API is active.")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
