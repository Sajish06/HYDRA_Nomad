# ASCENT Mock Meeting Fixtures for Pipeline Testing & Demo

This directory contains fabricated meeting transcripts and structured summaries used for automated unit/integration testing and end-to-end pipeline demonstration before connecting live Meetily AI audio ingestion.

---

## Fixture Index

| Fixture ID | Title | Formats | Primary Test Focus / ASCENT Capability |
| :--- | :--- | :--- | :--- |
| **MEET-001** | Customer Analytics Dashboard | [JSON](file:///c:/Users/Jeyaraman/OneDrive/Desktop/My-Projects/ASCENT/tests/fixtures/mock_meetings/transcript_1_customer_analytics.json), [Transcript MD](file:///c:/Users/Jeyaraman/OneDrive/Desktop/My-Projects/ASCENT/tests/fixtures/mock_meetings/transcript_1_customer_analytics.md), [Summary MD](file:///c:/Users/Jeyaraman/OneDrive/Desktop/My-Projects/ASCENT/tests/fixtures/mock_meetings/summary_1_customer_analytics.md) | **Requirement Creation & Privacy Scrubbing**: Confirms revenue RBAC restriction (`ADMIN`, `FINANCE`) while masking confidential commercial acquisition negotiation context. |
| **MEET-002** | API Performance Discussion | [JSON](file:///c:/Users/Jeyaraman/OneDrive/Desktop/My-Projects/ASCENT/tests/fixtures/mock_meetings/transcript_2_api_performance.json), [Transcript MD](file:///c:/Users/Jeyaraman/OneDrive/Desktop/My-Projects/ASCENT/tests/fixtures/mock_meetings/transcript_2_api_performance.md), [Summary MD](file:///c:/Users/Jeyaraman/OneDrive/Desktop/My-Projects/ASCENT/tests/fixtures/mock_meetings/summary_2_api_performance.md) | **Uncertainty & Decision Gating**: Resolves conversational oscillations. Evaluates Redis caching proposal as `PROPOSED` / `PENDING_BENCHMARK` rather than prematurely locking it into active system architecture. |
| **MEET-003** | Analytics Dashboard Follow-up | [JSON](file:///c:/Users/Jeyaraman/OneDrive/Desktop/My-Projects/ASCENT/tests/fixtures/mock_meetings/transcript_3_analytics_followup.json), [Transcript MD](file:///c:/Users/Jeyaraman/OneDrive/Desktop/My-Projects/ASCENT/tests/fixtures/mock_meetings/transcript_3_analytics_followup.md), [Summary MD](file:///c:/Users/Jeyaraman/OneDrive/Desktop/My-Projects/ASCENT/tests/fixtures/mock_meetings/summary_3_analytics_followup.md) | **Requirement Evolution & Memory Update**: Tests incremental graph evolution where previous RBAC constraints from MEET-001 are modified to grant `SUPPORT_LEAD` access to monthly summary metrics without rebuilding backend components. |

---

## JSON Schema Specification (Meetily Native Format)

All JSON fixture files adhere to the Meetily export structure:

```json
{
  "source": "meetily",
  "meeting_id": "string",
  "title": "string",
  "meeting_date": "ISO-8601 string",
  "duration_seconds": "integer",
  "participants": [
    { "name": "string", "role": "string" }
  ],
  "segments": [
    {
      "segment_id": "string",
      "speaker": "string",
      "start_time": "float",
      "end_time": "float",
      "text": "string"
    }
  ]
}
```
