import uuid
from pathlib import Path
from typing import List, Dict
from app.masking.models import AgentTaskPayload, AgentRoleBrief, VerifiedCommitment, PersonWorkPacket

class PersonaSplitter:
    """
    Partitions normalized, clean AgentTaskPayload into role-tailored and person-tailored briefs.
    Outputs briefs with zero confidential business disclosures.
    """
    @staticmethod
    def split_task_by_assignee(
        payload: AgentTaskPayload,
        commitment: VerifiedCommitment,
        meeting_id: str
    ) -> List[AgentRoleBrief]:
        role_briefs = []

        for assignee in commitment.assignees:
            role_upper = assignee.role.upper()
            brief_id = f"BRIEF-{meeting_id}-{payload.task_id}-{role_upper}-{uuid.uuid4().hex[:6]}"
            
            # Find deliverables relevant to this role
            role_deliverables = [
                d for d in payload.things_to_implement
                if d.upper().startswith(f"{role_upper}:") or assignee.name.lower() in d.lower()
            ]
            if not role_deliverables:
                role_deliverables = [f"{role_upper}: {assignee.assigned_work}"]

            # Filter relevant technical context for this role
            role_briefs.append(AgentRoleBrief(
                brief_id=brief_id,
                task_id=payload.task_id,
                meeting_id=meeting_id,
                role=role_upper,
                assignee_name=assignee.name,
                actionable_deliverables=role_deliverables,
                technical_context=payload.technical_context,
                deadline=assignee.deadline or payload.deadline
            ))

        return role_briefs

    @staticmethod
    def group_by_person(
        role_briefs: List[AgentRoleBrief],
        meeting_id: str
    ) -> List[PersonWorkPacket]:
        """
        Consolidates role briefs across multiple tasks by individual person.
        Produces a single PersonWorkPacket per person containing all their assigned deliverables,
        deadlines, and relevant technical context.
        """
        people_map: Dict[str, Dict] = {}

        for brief in role_briefs:
            key = f"{brief.assignee_name}_{brief.role}"
            if key not in people_map:
                people_map[key] = {
                    "person_name": brief.assignee_name,
                    "role": brief.role,
                    "meeting_id": meeting_id,
                    "assigned_deliverables": [],
                    "technical_context": set(),
                    "deadlines": set()
                }

            # Add deliverables
            for d in brief.actionable_deliverables:
                if d not in people_map[key]["assigned_deliverables"]:
                    people_map[key]["assigned_deliverables"].append(d)

            # Add technical context
            for tc in brief.technical_context:
                people_map[key]["technical_context"].add(tc)

            # Add deadline
            if brief.deadline:
                people_map[key]["deadlines"].add(brief.deadline)

        person_packets = []
        for p in people_map.values():
            person_packets.append(PersonWorkPacket(
                person_name=p["person_name"],
                role=p["role"],
                meeting_id=p["meeting_id"],
                assigned_deliverables=p["assigned_deliverables"],
                technical_context=sorted(list(p["technical_context"])),
                deadlines=sorted(list(p["deadlines"]))
            ))

        return person_packets

    @staticmethod
    def export_person_briefs(
        person_packets: List[PersonWorkPacket],
        output_dir: Path
    ) -> List[Path]:
        """
        Exports clean, individual Markdown work briefs for each person.
        Each file contains only that person's deliverables and context.
        """
        output_dir.mkdir(parents=True, exist_ok=True)
        created_paths = []

        for packet in person_packets:
            safe_name = packet.person_name.replace(" ", "_")
            file_path = output_dir / f"{safe_name}_{packet.role}.md"
            
            lines = [
                f"# Work Packet: {packet.person_name} ({packet.role})",
                f"",
                f"**Meeting ID**: `{packet.meeting_id}`  ",
                f"**Role**: `{packet.role}`  ",
                f"**Deadlines**: {', '.join(packet.deadlines) if packet.deadlines else 'Not specified'}  ",
                f"",
                f"---",
                f"",
                f"## 🎯 Actionable Deliverables",
                f""
            ]
            for item in packet.assigned_deliverables:
                lines.append(f"- [ ] {item}")
            lines.append("")

            if packet.technical_context:
                lines.append(f"## ⚙️ Technical Constraints & Context")
                lines.append("")
                for tc in packet.technical_context:
                    lines.append(f"- {tc}")
                lines.append("")

            with open(file_path, "w", encoding="utf-8") as f:
                f.write("\n".join(lines))

            packet.markdown_path = str(file_path)
            created_paths.append(file_path)

        return created_paths

