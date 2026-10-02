"""Destination and connector configuration endpoints."""

from fastapi import APIRouter

router = APIRouter(prefix="/api/destinations", tags=["destinations"])


@router.get("")
async def list_destinations():
    """List active output destinations."""
    return {
        "destinations": [
            {
                "id": "local_disk",
                "type": "filesystem",
                "path": "./data/outputs",
                "status": "active",
                "audiences": ["deal_team", "outside_counsel", "lender", "board", "cloud_llm"],
            },
            {
                "id": "slack_sink",
                "type": "slack_webhook",
                "status": "planned",
                "note": "Modular sink connector interface ready for external webhook integration.",
            },
        ]
    }
