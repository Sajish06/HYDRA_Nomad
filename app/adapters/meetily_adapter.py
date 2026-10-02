import re
import httpx
from typing import List, Dict, Any, Optional
from app.models import Meeting, Segment, Participant
from app.adapters.base import MeetingAdapter
from app.config import settings

class MeetilyAdapter(MeetingAdapter):
    def __init__(self, base_url: Optional[str] = None, token: Optional[str] = None):
        self.base_url = (base_url or settings.MEETILY_URL).rstrip("/")
        self.token = token or settings.MEETILY_TOKEN

    def _headers(self) -> Dict[str, str]:
        headers = {"Accept": "application/json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    def list_meetings(self) -> List[Dict[str, Any]]:
        with httpx.Client(timeout=10.0) as client:
            resp = client.get(f"{self.base_url}/v1/meetings", headers=self._headers())
            resp.raise_for_status()
            data = resp.json()
            return data.get("meetings", [])

    def load(self, meeting_id: str) -> Meeting:
        with httpx.Client(timeout=15.0) as client:
            # 1. Fetch transcript
            t_resp = client.get(f"{self.base_url}/v1/meetings/{meeting_id}/transcript", headers=self._headers())
            t_resp.raise_for_status()
            t_data = t_resp.json()

            title = t_data.get("title") or f"Meeting {meeting_id}"
            raw_segs = t_data.get("segments", [])

            segments = []
            for i, s in enumerate(raw_segs):
                time_str = s.get("time") or s.get("start")
                t_sec = s.get("t_seconds") or s.get("start_seconds")
                segments.append(Segment(
                    idx=i,
                    speaker=s.get("speaker"),
                    time=str(time_str) if time_str is not None else None,
                    t_seconds=float(t_sec) if t_sec is not None else None,
                    text=s.get("text", "").strip()
                ))

            # 2. Fetch summary
            decisions = []
            actions = []
            try:
                s_resp = client.get(f"{self.base_url}/v1/meetings/{meeting_id}/summary", headers=self._headers())
                if s_resp.status_code == 200:
                    s_data = s_resp.json()
                    res = s_data.get("result", "")
                    if isinstance(res, dict):
                        decisions = res.get("decisions", [])
                        actions = res.get("action_items", [])
                    elif isinstance(res, str):
                        # Tolerant markdown parsing
                        lines = res.split("\n")
                        current_cat = None
                        for line in lines:
                            l = line.strip()
                            if re.search(r"decision", l, re.IGNORECASE):
                                current_cat = "dec"
                            elif re.search(r"action", l, re.IGNORECASE):
                                current_cat = "act"
                            elif l.startswith(("-", "*", "1.", "2.", "3.", "4.")):
                                bullet = re.sub(r"^[-*\d\.]+\s*", "", l)
                                if current_cat == "dec":
                                    decisions.append(bullet)
                                elif current_cat == "act":
                                    actions.append(bullet)
            except Exception:
                pass

            return Meeting(
                meeting_id=meeting_id,
                title=title,
                participants=[],
                segments=segments,
                summary_decisions=decisions,
                summary_actions=actions
            )
