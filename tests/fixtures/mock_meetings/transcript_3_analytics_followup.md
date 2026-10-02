# Transcript 3: Analytics Dashboard Follow-up

**Meeting**: Analytics Dashboard Follow-up  
**Meeting ID**: MEET-20261001-03  
**Date**: 2026-10-01  
**Participants**:
- **Maya**: Client
- **Arjun**: Project Lead
- **Ravi**: Backend Developer
- **Neha**: Frontend Developer

---

## Verbatim Dialogue

**[00:00] Maya**:  
I wanted to revisit the revenue analytics access.

**[00:05] Arjun**:  
The current requirement is that admins and finance managers can access those metrics, while support users cannot.

**[00:10] Maya**:  
Yes, that's right.

**[00:13] Maya**:  
But our customer support leads now need access to the monthly revenue summary as well. They don't need the detailed customer-value breakdown.

**[00:22] Arjun**:  
So you're changing the existing access rule rather than creating a completely new analytics feature?

**[00:27] Maya**:  
Correct.

**[00:29] Arjun**:  
And they should only get the monthly summary?

**[00:32] Maya**:  
Exactly.

**[00:35] Ravi**:  
The existing backend authorization is already implemented.

**[00:38] Arjun**:  
Then we shouldn't build the authorization system again.

**[00:41] Ravi**:  
Right. We only need to modify the permission for the monthly summary endpoint.

**[00:46] Neha**:  
And I'll update the dashboard so support leads see the monthly summary but not the detailed revenue cards.

**[00:51] Arjun**:  
Good. QA should also test that normal support users still don't get access.

**[00:56] Maya**:  
Yes.

**[00:58] Arjun**:  
Let's make that the change for this release.
