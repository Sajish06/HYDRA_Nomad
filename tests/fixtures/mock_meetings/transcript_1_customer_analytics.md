# Meeting Transcript 1: Customer Analytics Dashboard

**Meeting Title**: Customer Analytics Dashboard  
**Meeting ID**: `MEET-001`  
**Date**: 2026-10-01  
**Source Platform**: Meetily AI Audio-to-Transcript Engine (Local Loopback Ingestion)  

---

### Attendees
- **Maya** — *Client*
- **Arjun** — *Project Lead (Host)*
- **Ravi** — *Backend Developer*
- **Neha** — *Frontend Developer*

---

### Verbatim Transcript

**[00:00] Maya:**  
The analytics dashboard needs one change before the next release. Customer revenue information shouldn't be visible to everyone.

**[00:12] Arjun:**  
Is this about all analytics or specifically the revenue-related metrics?

**[00:17] Maya:**  
Specifically revenue, average order value, and the monthly customer value figures.

**[00:26] Arjun:**  
Okay. What's driving the restriction?

**[00:31] Maya:**  
We are expanding into two new markets next month, and our customer numbers are expected to increase significantly. Some of our internal sales information is sensitive because we're negotiating with another company right now. I don't want ordinary support staff seeing the revenue numbers.

**[00:48] Arjun:**  
Understood. So support staff shouldn't see those metrics, but administrators should?

**[00:52] Maya:**  
Yes. Admins and finance managers can see them. Regular support users shouldn't.

**[01:00] Ravi:**  
We already have the RBAC system with ADMIN and FINANCE roles. We could enforce the restriction at the API level rather than changing authentication.

**[01:08] Arjun:**  
That sounds reasonable. Does the frontend also need to hide the cards?

**[01:12] Neha:**  
Yes. If the API denies access but the cards remain visible, users will just see errors.

**[01:17] Arjun:**  
Then let's do both. Ravi, handle the API authorization. Neha, hide the revenue cards for unauthorized users.

**[01:24] Ravi:**  
I'll take the backend part. I'll check the existing RBAC middleware and update the relevant analytics endpoints.

**[01:29] Neha:**  
I'll update the dashboard components.

**[01:34] Arjun:**  
Neha, can you also add the unauthorized-state handling?

**[01:38] Neha:**  
Yes.

**[01:41] Arjun:**  
Ravi, have this ready by Friday. Neha, same deadline.

**[01:45] Ravi:**  
Okay.

**[01:47] Neha:**  
Done.

**[01:50] Arjun:**  
QA should verify that admins and finance managers can see the metrics and support users cannot.
