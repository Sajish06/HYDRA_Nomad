# 🛡️ Sanitized Task Briefing: Customer Analytics Dashboard
> **Meeting ID**: `MEET-20261001-01`  
> **Privacy Gate Status**: `PASS (ALL SENSITIVE DATA MASKED)`  
> **Entities Masked**: `15` tokens registered in local offline vault  
> **Vault Path**: `data\vaults\vault_MEET-20261001-01.json`  

---
## 📋 Masked Tasks & Role Assignments

### Task `TASK-001`
**Sanitized Requirement:**
> Customer revenue, [METRIC_2], and [METRIC_1] should not be visible to ordinary support staff, only to admins and finance managers.

**Role Assignments:**
- **[BACKEND]** `[PERSON_1]`: Update RBAC middleware and analytics API endpoints to enforce [METRIC_3] authorization. (Deadline: `Friday`)
- **[FRONTEND]** `[PERSON_2]`: Update dashboard UI components to conditionally hide [METRIC_4] and handle unauthorized error states. (Deadline: `Friday`)
- **[QA]** `[PERSON_3]`: Verify ADMIN and FINANCE roles receive revenue metrics, while SUPPORT role cannot access metrics. (Deadline: `Friday`)

**Grounding Evidence Quotes (Sanitized):**
- Maya: We are expanding into two new markets next month, and our customer numbers are expected to increase significantly. Some of our internal [METRIC_6] is sensitive because we're negotiating with another company right now. I don't want ordinary support staff seeing the [METRIC_5].
- [PERSON_1]: We already have the RBAC system with ADMIN and FINANCE roles. We could enforce the restriction at the API level rather than changing authentication.
- Arjun: Then let's do both. [PERSON_1], handle the API authorization. [PERSON_2], hide the [METRIC_4] for unauthorized users.
- Arjun: [PERSON_1], have this ready by Friday. [PERSON_2], same deadline.
- Arjun: QA should verify that admins and finance managers can see the metrics and support users cannot.

---

## 👥 Role-Specific Fan-out View

### Role: `BACKEND` (1 items)
- **Task `TASK-001`** ([PERSON_1]): Update RBAC middleware and analytics API endpoints to enforce [METRIC_3] authorization.

### Role: `FRONTEND` (1 items)
- **Task `TASK-001`** ([PERSON_2]): Update dashboard UI components to conditionally hide [METRIC_4] and handle unauthorized error states.

### Role: `QA` (1 items)
- **Task `TASK-001`** ([PERSON_3]): Verify ADMIN and FINANCE roles receive revenue metrics, while SUPPORT role cannot access metrics.
