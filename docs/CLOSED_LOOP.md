# Nomad Clean Room: Closed-Loop Tool Contracts & Protocol Specification

This document details the tool contracts, message payloads, error responses, and state machine invariants for external coding agents (e.g. Google Antigravity) communicating with Nomad over the Model Context Protocol (MCP stdio).

---

## 1. Tool Contracts

### 1.1 `cleanroom_get_masked_brief`

Pulls the compiled build brief for a verified meeting. AGY calls this tool first to begin a coding session.

#### Parameters

| Field | Type | Required | Description |
| :--- | :--- | :--- | :--- |
| `meeting_id` | `string` | **Yes** | Unique identifier of the verified meeting. |
| `loop_run_id` | `string` | No | ID of an existing active run to resume. If omitted, starts a new run. |
| `task_id` | `string` | No | Optional filter to build a single specific task from the meeting. |

#### Successful Return Payload Example

```json
{
  "loop_run_id": "f1da23ae-a0aa-40cb-ac61-944ac77b94d0",
  "meeting_id": "mtg_alpha_001",
  "iteration": 1,
  "max_iterations": 3,
  "workspace_path": "C:\\Users\\DELL\\Desktop\\test\\run_mtg_alpha_001_1790991524",
  "prompt": {
    "objective": "Implement static web deliverables (index.html, contact.html) according to verified meeting specifications.",
    "context": "Customer [COMPANY_1] requires a responsive landing page and contact form.",
    "requirements": [
      "Create landing page index.html with header, about section, 3 features, and footer",
      "Create contact.html with a form containing name, email, message fields and submit button",
      "Do not use external CDN or remote resources"
    ],
    "constraints": [
      "Deliverables must be written strictly inside workspace path",
      "All links must resolve locally",
      "Form inputs must have explicit labels or aria-labels"
    ],
    "deliverables": [
      "index.html",
      "contact.html"
    ],
    "acceptance_criteria": [
      "Deliverable index.html must exist as a file",
      "index.html must have valid HTML structure with non-empty <title>",
      "Deliverable contact.html must exist as a file",
      "contact.html form inputs must have associated labels",
      "No external http/https/cdn resources"
    ],
    "out_of_scope": [
      "Backend server scripts",
      "Unverified marketing budget widgets"
    ],
    "workspace_instructions": "Build your code strictly inside: C:\\Users\\DELL\\Desktop\\test\\run_mtg_alpha_001_1790991524. NEVER write outside this path.",
    "reporting_instructions": "Upon completion, call cleanroom_submit_code_report with loop_run_id, agy_status, summary, and files_changed list.",
    "iteration": 1,
    "previous_feedback": ""
  },
  "acceptance_criteria": [
    {
      "id": "crit_01_index_html",
      "description": "index.html must exist and contain valid HTML",
      "target_file": "index.html"
    }
  ],
  "excluded_tasks": [
    {
      "task_id": "task_unverified_budget",
      "title": "Allocate $50k marketing budget",
      "reason": "Verification status is 'contradicted' against transcript evidence."
    }
  ],
  "source": "fallback",
  "gate": {
    "decision": "release",
    "rationale": "All tasks verified and masked."
  }
}
```

#### Error Payload Example (Gate Blocked or Closed Loop)

```json
{
  "isError": true,
  "error": "Access Denied: Meeting mtg_blocked_002 has review gate decision 'block'. Cannot issue build brief until reviewed and approved."
}
```

---

### 1.2 `cleanroom_submit_code_report`

Reports code deliverables produced by AGY. Triggers Nomad's independent acceptance test suite in a sandboxed, scrubbed subprocess.

#### Parameters

| Field | Type | Required | Description |
| :--- | :--- | :--- | :--- |
| `loop_run_id` | `string` | **Yes** | Active loop run identifier from `cleanroom_get_masked_brief`. |
| `agy_status` | `string` | **Yes** | One of `completed`, `partial`, `blocked`, or `failed`. |
| `summary` | `string` | **Yes** | Agent summary of actions performed. |
| `files_changed` | `array[string]` | **Yes** | Relative file paths created or edited in the workspace. |
| `diff` | `string` | No | Optional unified diff of changes made. |
| `test_results` | `object` | No | Informational self-reported test results (untrusted by Nomad). |

#### Return Payload Examples

##### Verdict: `revise` (Tests Failed, Iterations Remaining)

```json
{
  "verdict": "revise",
  "iteration": 1,
  "remaining_iterations": 2,
  "evaluation": {
    "passed_count": 8,
    "failed_count": 2,
    "tamper_findings": [],
    "out_of_workspace_findings": [],
    "leak_findings": [],
    "failures": [
      {
        "test": "test_02_html_title_nonempty_index_html",
        "message": "AssertionError: Missing <title> tag in index.html"
      },
      {
        "test": "test_05_html_form_has_labeled_inputs_contact_html",
        "message": "AssertionError: Found unlabeled form input(s) in contact.html: ['email']"
      }
    ]
  },
  "next_prompt": {
    "objective": "Implement static web deliverables (index.html, contact.html) according to verified meeting specifications.",
    "iteration": 2,
    "previous_feedback": "The previous build had 2 failed criteria:\n1. Missing <title> tag in index.html\n2. Found unlabeled form input(s) in contact.html: ['email']\n\nPlease fix these issues strictly inside your workspace.",
    "workspace_instructions": "Continue editing deliverables inside: C:\\Users\\DELL\\Desktop\\test\\run_mtg_alpha_001_1790991524."
  },
  "ledger_entry_hash": "56014cf06e5529e1f..."
}
```

##### Verdict: `passed` (All Acceptance Criteria Met)

```json
{
  "verdict": "passed",
  "iteration": 2,
  "remaining_iterations": 0,
  "evaluation": {
    "passed_count": 10,
    "failed_count": 0,
    "tamper_findings": [],
    "out_of_workspace_findings": [],
    "leak_findings": [],
    "failures": []
  },
  "next_prompt": null,
  "ledger_entry_hash": "c9907c35196342db1..."
}
```

##### Verdict: `failed_max_iterations` (Iteration Cap Reached)

```json
{
  "verdict": "failed_max_iterations",
  "iteration": 3,
  "remaining_iterations": 0,
  "evaluation": {
    "passed_count": 8,
    "failed_count": 2,
    "failures": [
      {
        "test": "test_02_html_title_nonempty_index_html",
        "message": "AssertionError: Missing <title> tag in index.html"
      }
    ]
  },
  "next_prompt": null,
  "ledger_entry_hash": "e148df2944b02c89a..."
}
```

##### Verdict: `rejected` (Security Violation: Tamper or Path Traversal)

```json
{
  "verdict": "rejected",
  "iteration": 1,
  "remaining_iterations": 0,
  "evaluation": {
    "tamper_findings": [
      "Tamper detected: tests_nomad\\test_acceptance.py was modified or deleted by agent."
    ],
    "out_of_workspace_findings": [
      "Illegal path reported outside workspace: ..\\..\\secret.txt"
    ]
  },
  "next_prompt": null,
  "ledger_entry_hash": "a4d87130fca68341..."
}
```

---

### 1.3 `cleanroom_get_loop_status`

Queries current status, iteration count, and execution history of an active or completed loop run.

#### Parameters

| Field | Type | Required | Description |
| :--- | :--- | :--- | :--- |
| `loop_run_id` | `string` | **Yes** | Active or terminal loop run identifier. |

#### Return Payload Example

```json
{
  "loop_run_id": "f1da23ae-a0aa-40cb-ac61-944ac77b94d0",
  "meeting_id": "mtg_alpha_001",
  "status": "passed",
  "iteration": 2,
  "max_iterations": 3,
  "workspace_path": "C:\\Users\\DELL\\Desktop\\test\\run_mtg_alpha_001_1790991524",
  "history": [
    {"iteration": 1, "verdict": "revise", "passed": 8, "failed": 2},
    {"iteration": 2, "verdict": "passed", "passed": 10, "failed": 0}
  ]
}
```

---

### 1.4 `cleanroom_abort_loop`

Allows an operator or agent to explicitly terminate a loop run.

#### Parameters

| Field | Type | Required | Description |
| :--- | :--- | :--- | :--- |
| `loop_run_id` | `string` | **Yes** | Loop run identifier to abort. |
| `reason` | `string` | No | Reason for aborting (default: `"Aborted by client"`). |

#### Return Payload Example

```json
{
  "loop_run_id": "f1da23ae-a0aa-40cb-ac61-944ac77b94d0",
  "status": "aborted",
  "reason": "Aborted by client",
  "ledger_entry_hash": "887aef4109..."
}
```

---

## 2. Server-Side State Machine Invariants

1. **Iteration Cap:** `MAX_ITERATIONS` defaults to 3 and can be configured lower, but never higher. When `iteration == 3` and tests fail, the server transitions directly to `failed_max_iterations`. An iteration 4 is impossible.
2. **Idempotent Reports:** If an agent submits duplicate reports for the same iteration, the server returns the existing evaluation verdict and does not increment iteration counter.
3. **Stale Session Handling:** Any report submitted for an unknown or already-terminal `loop_run_id` returns a structured MCP error result.
4. **Offline Resilience:** All tool functions execute fully offline without requiring internet access, remote API endpoints, or Gemini keys.
