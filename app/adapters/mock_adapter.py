import re
import json
import uuid
from pathlib import Path
from typing import Union, Dict, Any, Optional, List
from app.models import Meeting, Segment, Participant
from app.adapters.base import MeetingAdapter

def parse_time_to_seconds(time_str: Optional[Union[str, int, float]]) -> Optional[float]:
    if time_str is None:
        return None
    if isinstance(time_str, (int, float)):
        return float(time_str)
    
    parts = str(time_str).strip().split(":")
    try:
        if len(parts) == 1:
            return float(parts[0])
        elif len(parts) == 2:
            return float(parts[0]) * 60 + float(parts[1])
        elif len(parts) == 3:
            return float(parts[0]) * 3600 + float(parts[1]) * 60 + float(parts[2])
    except ValueError:
        return None
    return None

def parse_transcript_text_to_segments(text: str) -> List[Segment]:
    """Parses raw plain text transcript lines into structured Segment objects."""
    lines = [l.strip() for l in text.split("\n") if l.strip()]
    segments = []
    
    for i, line in enumerate(lines):
        # Match pattern like: "Alice (10:15): We should do X" or "Alice [10:15]: We should do X" or "Alice: We should do X"
        m = re.match(r"^([A-Za-z0-9\s_-]+?)(?:\s*[\(\[]([0-9:]+)[\)\]])?\s*:\s*(.*)$", line)
        if m:
            speaker = m.group(1).strip()
            time_str = m.group(2)
            seg_text = m.group(3).strip()
        else:
            speaker = "Speaker"
            time_str = None
            seg_text = line

        t_sec = parse_time_to_seconds(time_str) if time_str else None
        segments.append(Segment(
            idx=i,
            speaker=speaker,
            time=time_str,
            t_seconds=t_sec,
            text=seg_text
        ))
    return segments

def normalize_summary_item(item: Any) -> Optional[str]:
    if item is None:
        return None
    if isinstance(item, str):
        s = item.strip()
        return s if s else None
    if isinstance(item, dict):
        if "claim" in item and item["claim"]:
            return str(item["claim"]).strip()

        # Check for task / description / action keys with possible assignee & deadline
        task_text = None
        for k in ("task", "description", "action", "decision", "text", "title", "content", "statement", "summary"):
            if k in item and item[k]:
                val = item[k]
                if isinstance(val, str) and val.strip():
                    task_text = val.strip()
                    break
                elif isinstance(val, (int, float, bool)):
                    task_text = str(val)
                    break

        if task_text:
            owner = item.get("owner") or item.get("assignee") or item.get("actor")
            due = item.get("due_date") or item.get("deadline") or item.get("due")
            res = task_text
            if owner and isinstance(owner, str) and not task_text.lower().startswith(owner.lower()):
                res = f"{owner.strip()} will {task_text.rstrip('.')}"
            if due and isinstance(due, str) and due not in res:
                res = f"{res} by {due.strip()}"
            return res

        vals = [str(v).strip() for v in item.values() if v is not None and str(v).strip()]
        if vals:
            return " - ".join(vals)
        return json.dumps(item)
    return str(item).strip()

class MockAdapter(MeetingAdapter):
    def load(self, source: Union[str, Path, Dict[str, Any], List[Any]]) -> Meeting:
        if isinstance(source, (str, Path)):
            path = Path(source)
            if not path.is_absolute():
                from app.config import BASE_DIR
                candidate = BASE_DIR / "data" / "mock" / path.name
                if candidate.exists():
                    path = candidate
            
            with open(path, "r", encoding="utf-8") as f:
                content = f.read().strip()
                try:
                    data = json.loads(content)
                except json.JSONDecodeError:
                    # Treat as plain text raw transcript
                    data = {
                        "meeting_id": f"CUSTOM_{uuid.uuid4().hex[:6].upper()}",
                        "title": path.stem,
                        "raw_transcript": content
                    }
        elif isinstance(source, dict):
            data = source
        elif isinstance(source, list):
            data = {"segments": source}
        else:
            raise ValueError(f"Unsupported source type: {type(source)}")

        meeting_id = data.get("meeting_id") or data.get("id") or f"MEETING_{uuid.uuid4().hex[:6].upper()}"
        title = data.get("title") or f"Meeting {meeting_id}"

        # Participants
        participants_data = data.get("participants") or []
        participants = []
        for p in participants_data:
            if isinstance(p, dict):
                participants.append(Participant(
                    name=p.get("name") or p.get("speaker") or "Unknown",
                    role=p.get("role"),
                    has_authority=bool(p.get("has_authority", True))
                ))
            elif isinstance(p, str):
                participants.append(Participant(name=p, has_authority=True))

        if not participants:
            raw_segs = data.get("segments") or []
            if isinstance(raw_segs, dict):
                raw_segs = list(raw_segs.values())
            seen_speakers = set()
            for s in raw_segs:
                spk = s.get("speaker") if isinstance(s, dict) else None
                if spk and spk not in seen_speakers:
                    seen_speakers.add(spk)
                    participants.append(Participant(name=spk, has_authority=True))

        # Segments
        segments = []
        if "raw_transcript" in data and isinstance(data["raw_transcript"], str):
            segments = parse_transcript_text_to_segments(data["raw_transcript"])
        elif "transcript" in data and isinstance(data["transcript"], str):
            segments = parse_transcript_text_to_segments(data["transcript"])
        else:
            raw_segments = data.get("segments") or data.get("transcript") or []
            if isinstance(raw_segments, dict):
                raw_segments = list(raw_segments.values())

            for i, s in enumerate(raw_segments):
                if isinstance(s, str):
                    # string segment e.g. "Alice: text"
                    m = re.match(r"^([A-Za-z0-9\s_-]+?)(?:\s*[\(\[]([0-9:]+)[\)\]])?\s*:\s*(.*)$", s)
                    if m:
                        spk = m.group(1).strip()
                        t_str = m.group(2)
                        txt = m.group(3).strip()
                    else:
                        spk = None
                        t_str = None
                        txt = s
                    segments.append(Segment(
                        idx=i,
                        speaker=spk,
                        time=t_str,
                        t_seconds=parse_time_to_seconds(t_str) if t_str else None,
                        text=txt
                    ))
                elif isinstance(s, dict):
                    raw_idx = s.get("idx") if s.get("idx") is not None else (s.get("segment_id") or s.get("id"))
                    if raw_idx is not None:
                        try:
                            idx_val = int(raw_idx)
                        except (ValueError, TypeError):
                            digits = re.findall(r"\d+", str(raw_idx))
                            idx_val = int(digits[0]) if digits else i
                    else:
                        idx_val = i

                    time_val = s.get("time") or s.get("timestamp") or s.get("start")
                    t_sec = s.get("t_seconds")
                    if t_sec is None and time_val is not None:
                        t_sec = parse_time_to_seconds(time_val)
                    
                    speaker_val = s.get("speaker") or s.get("name") or s.get("user")
                    text_val = str(s.get("text") or s.get("content") or s.get("utterance") or s.get("body") or "").strip()
                    
                    segments.append(Segment(
                        idx=idx_val,
                        speaker=str(speaker_val) if speaker_val else None,
                        time=str(time_val) if time_val is not None else None,
                        t_seconds=t_sec,
                        text=text_val
                    ))

        # Ensure segments are sorted by idx
        segments.sort(key=lambda x: x.idx)

        # Summary
        summary_data = data.get("summary") or {}
        raw_decisions = []
        raw_actions = []

        if isinstance(summary_data, dict):
            test_cases = summary_data.get("expected_test_cases") or summary_data.get("test_cases") or summary_data.get("claims") or data.get("expected_test_cases") or data.get("claims")
            if test_cases:
                tc_list = test_cases if isinstance(test_cases, list) else [test_cases]
                for tc in tc_list:
                    if isinstance(tc, dict) and (tc.get("category") in ("commitment", "action") or "task" in tc):
                        raw_actions.append(tc)
                    else:
                        raw_decisions.append(tc)
            else:
                dec = summary_data.get("decisions") or summary_data.get("key_decisions") or summary_data.get("key_points") or summary_data.get("points") or summary_data.get("takeaways") or data.get("summary_decisions") or []
                if isinstance(dec, list):
                    raw_decisions.extend(dec)
                elif dec:
                    raw_decisions.append(dec)

                act = summary_data.get("action_items") or summary_data.get("actions") or summary_data.get("tasks") or data.get("summary_actions") or []
                if isinstance(act, list):
                    raw_actions.extend(act)
                elif act:
                    raw_actions.append(act)

            if not raw_decisions and not raw_actions:
                stext = summary_data.get("summary_text") or (summary_data.get("summary") if isinstance(summary_data.get("summary"), str) else None)
                if stext and isinstance(stext, str):
                    raw_decisions = [s.strip() for s in re.split(r"(?<=[.!?])\s+", stext) if s.strip()]
        elif isinstance(summary_data, list):
            raw_decisions = summary_data
        elif isinstance(summary_data, str):
            lines = [l.strip().lstrip("-*123456789. ") for l in summary_data.split("\n") if l.strip()]
            raw_decisions = lines
        else:
            raw_decisions = data.get("summary_decisions") or []
            raw_actions = data.get("summary_actions") or []

        summary_decisions = []
        for it in raw_decisions:
            norm = normalize_summary_item(it)
            if norm:
                summary_decisions.append(norm)

        summary_actions = []
        for it in raw_actions:
            norm = normalize_summary_item(it)
            if norm:
                summary_actions.append(norm)

        return Meeting(
            meeting_id=meeting_id,
            title=title,
            participants=participants,
            segments=segments,
            summary_decisions=summary_decisions,
            summary_actions=summary_actions
        )
