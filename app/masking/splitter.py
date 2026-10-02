from typing import List, Dict, Any
from app.masking.models import SanitizedTask, SanitizedAssignee

class RoleSplitter:
    """Splits sanitized tasks and work items across specialized personas (Backend, Frontend, QA, etc.)."""

    @staticmethod
    def split_by_role(tasks: List[SanitizedTask]) -> Dict[str, List[Dict[str, Any]]]:
        role_map: Dict[str, List[Dict[str, Any]]] = {}

        for task in tasks:
            for assignee in task.assignees:
                role = (assignee.role or "GENERAL").upper()
                if role not in role_map:
                    role_map[role] = []
                
                role_map[role].append({
                    "task_id": task.task_id,
                    "masked_requirement": task.masked_requirement,
                    "assignee_name": assignee.name,
                    "assigned_work": assignee.assigned_work,
                    "deadline": assignee.deadline,
                    "evidence_quotes": task.masked_evidence_quotes
                })

        return role_map
