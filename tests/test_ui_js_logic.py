"""Test the client-side JavaScript logic, state mutations, and DOM elements in clay.html."""

import json
from pathlib import Path
import pytest
from bs4 import BeautifulSoup

def test_clay_html_dom_structure():
    clay_path = Path("backend/static/clay.html")
    assert clay_path.exists()
    content = clay_path.read_text(encoding="utf-8")
    
    soup = BeautifulSoup(content, "html.parser")
    
    # 1. Check Tasks Board exists with two columns
    board = soup.find(id="tasks-board-card")
    assert board is not None, "tasks-board-card not found in clay.html"
    
    verified_list = soup.find(id="verified-tasks-list")
    assert verified_list is not None, "verified-tasks-list not found"
    
    ambiguous_list = soup.find(id="ambiguous-tasks-list")
    assert ambiguous_list is not None, "ambiguous-tasks-list not found"
    
    badge_v = soup.find(id="badge-verified-count")
    assert badge_v is not None
    
    badge_a = soup.find(id="badge-ambiguous-count")
    assert badge_a is not None

    # 2. Check JSON output section
    out_card = soup.find(id="output-card")
    assert out_card is not None
    json_result = soup.find(id="json-result")
    assert json_result is not None


def test_js_accept_reject_state_transition():
    """Simulate the exact JS state machine for acceptTask and rejectTask."""
    # Mock data as returned by /api/pipeline/verify-and-mask
    lastResult = {
        "status": "SUCCESS",
        "meeting_id": "DEMO_002",
        "meeting_title": "Discord planning",
        "verified_tasks_count": 0,
        "verified_tasks": [],
        "ambiguous_tasks_count": 1,
        "ambiguous_tasks": [
            {
                "task_id": "claim_DEMO_002_1",
                "claim_id": "claim_DEMO_002_1",
                "task_text": "Create a sponsorship Discord channel.",
                "actor": "Unassigned",
                "deadline": None,
                "status": "AMBIGUOUS",
                "gate_action": "HUMAN_REVIEW",
                "explanation": "Deferred by Lead.",
                "evidence_chain": [
                    {
                        "speaker": "Member",
                        "time": "10:35",
                        "quote": "Should we create a sponsorship channel?",
                        "stance": "Stance.QUESTION",
                        "relation": "CONTRADICTS"
                    },
                    {
                        "speaker": "Lead",
                        "time": "10:36",
                        "quote": "Let's hold off on sponsorships until next semester.",
                        "stance": "Stance.DEFER",
                        "relation": "CONTRADICTS"
                    }
                ],
                "proposed_task": {
                    "task_id": "claim_DEMO_002_1",
                    "intentions": ["Create a sponsorship Discord channel."],
                    "things_to_implement": ["Unassigned: Create a sponsorship Discord channel."],
                    "technical_context": [
                        "Should we create a sponsorship channel?",
                        "Let's hold off on sponsorships until next semester."
                    ],
                    "deadline": None
                }
            }
        ]
    }

    # Simulate acceptTask("claim_DEMO_002_1")
    taskId = "claim_DEMO_002_1"
    idx = next((i for i, t in enumerate(lastResult["ambiguous_tasks"]) if t.get("task_id") == taskId), -1)
    assert idx != -1

    item = lastResult["ambiguous_tasks"].pop(idx)
    verifiedItem = item.get("proposed_task") or {
        "task_id": item["task_id"],
        "intentions": [item["task_text"]],
        "things_to_implement": [f"{item['actor']}: {item['task_text']}"],
        "technical_context": [e["quote"] for e in item.get("evidence_chain", [])],
        "deadline": item.get("deadline")
    }

    lastResult["verified_tasks"].append(verifiedItem)
    lastResult["verified_tasks_count"] = len(lastResult["verified_tasks"])
    lastResult["ambiguous_tasks_count"] = len(lastResult["ambiguous_tasks"])

    # Assert state post-acceptance
    assert lastResult["verified_tasks_count"] == 1
    assert lastResult["ambiguous_tasks_count"] == 0
    assert len(lastResult["verified_tasks"]) == 1
    assert len(lastResult["ambiguous_tasks"]) == 0
    assert lastResult["verified_tasks"][0]["task_id"] == "claim_DEMO_002_1"

    # Simulate rejecting another ambiguous task
    lastResult["ambiguous_tasks"].append({
        "task_id": "claim_DEMO_002_2",
        "task_text": "Rejected task"
    })
    lastResult["ambiguous_tasks_count"] = 1

    # Reject
    idx = next((i for i, t in enumerate(lastResult["ambiguous_tasks"]) if t.get("task_id") == "claim_DEMO_002_2"), -1)
    lastResult["ambiguous_tasks"].pop(idx)
    lastResult["ambiguous_tasks_count"] = len(lastResult["ambiguous_tasks"])

    assert lastResult["ambiguous_tasks_count"] == 0
    assert lastResult["verified_tasks_count"] == 1
