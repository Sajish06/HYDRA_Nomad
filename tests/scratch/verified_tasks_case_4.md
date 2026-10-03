# Verified Technical Specifications (Sanitized for Downstream AI)

**Meeting**: Customer Data Export Role Restriction  
**Meeting ID**: TEST_CASE_04  
**Privacy Boundary**: Enforced — Zero Business Secrets Disclosed  

---

## Task: TASK-004

### 1. Intentions (Technical Objective)
- SUPPORT users must no longer be able to export customer email addresses or phone numbers, restricting export capabilities strictly to ADMIN and CRM_MANAGER.

### 2. Things to Implement (Structured Deliverables)
- BACKEND: Update customer export endpoint authorization to restrict PII field exports strictly to ADMIN and CRM_MANAGER.
- FRONTEND: Remove export option from SUPPORT interface and show authorization error banner if requested directly.
- QA: Test both UI controls and direct API access across SUPPORT, ADMIN, and CRM_MANAGER roles.

### 3. Technical Context (Prerequisites & Constraints)

**Deadline**: Thursday

### 4. Role-Specific Briefs
#### BACKEND — Assignee: Ravi (Deadline: Thursday)
- Deliverable: BACKEND: Update customer export endpoint authorization to restrict PII field exports strictly to ADMIN and CRM_MANAGER.

#### FRONTEND — Assignee: Neha (Deadline: Thursday)
- Deliverable: FRONTEND: Remove export option from SUPPORT interface and show authorization error banner if requested directly.

#### QA — Assignee: QA_Team (Deadline: Thursday)
- Deliverable: QA: Test both UI controls and direct API access across SUPPORT, ADMIN, and CRM_MANAGER roles.

---

### Privacy Engine Audit
- Total Business Secrets Isolated & Dropped: **0**
- Downstream Leak Gate Status: **PASSED (Clean Technical Spec)**
