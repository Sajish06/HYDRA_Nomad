import pytest
from app.models import Stance
from app.analysis.cues import detect_primary_cue

def test_defer_cues():
    # Positive examples
    assert detect_primary_cue("Let's hold off on sponsorships until next semester.")["stance"] == Stance.DEFER
    assert detect_primary_cue("We should postpone this until next sprint.")["stance"] == Stance.DEFER
    assert detect_primary_cue("Let's table this for now.")["stance"] == Stance.DEFER
    assert detect_primary_cue("Not now, we will revisit later.")["stance"] == Stance.DEFER

def test_reject_cues():
    assert detect_primary_cue("Let's not build that feature.")["stance"] == Stance.REJECT
    assert detect_primary_cue("No, we shouldn't use MongoDB.")["stance"] == Stance.REJECT
    assert detect_primary_cue("That's against it, it won't work.")["stance"] == Stance.REJECT

def test_reverse_cues():
    assert detect_primary_cue("Actually, we decided not to use Redis.")["stance"] == Stance.REVERSE
    assert detect_primary_cue("We changed our mind on the database.")["stance"] == Stance.REVERSE
    assert detect_primary_cue("Never mind, we decided not to go with that.")["stance"] == Stance.REVERSE

def test_cancel_cues():
    assert detect_primary_cue("Let's drop that initiative.")["stance"] == Stance.CANCEL
    assert detect_primary_cue("We should scrap this plan.")["stance"] == Stance.CANCEL
    assert detect_primary_cue("The project is cancelled.")["stance"] == Stance.CANCEL

def test_decide_cues():
    assert detect_primary_cue("Let's definitely create dedicated teams for both.")["stance"] == Stance.DECIDE
    assert detect_primary_cue("We are going with PostgreSQL.")["stance"] == Stance.DECIDE
    assert detect_primary_cue("We decided to launch next month.")["stance"] == Stance.DECIDE

def test_commit_cues():
    assert detect_primary_cue("I'll handle the database migration.")["stance"] == Stance.COMMIT
    assert detect_primary_cue("I will investigate whether Redis works.")["stance"] == Stance.COMMIT
    assert detect_primary_cue("I can take this task.")["stance"] == Stance.COMMIT

def test_accept_cues():
    assert detect_primary_cue("Yes, I'll look into it.")["stance"] == Stance.ACCEPT
    assert detect_primary_cue("Sure, sounds good.")["stance"] == Stance.ACCEPT
    assert detect_primary_cue("Okay, agreed.")["stance"] == Stance.ACCEPT

def test_question_cues():
    assert detect_primary_cue("Should we create a sponsorship channel?")["stance"] == Stance.QUESTION
    assert detect_primary_cue("Can you investigate whether Redis works for rate limiting?")["stance"] == Stance.QUESTION

def test_negative_cues():
    assert detect_primary_cue("We discussed improving the website.") is None or detect_primary_cue("We discussed improving the website.")["stance"] not in (Stance.DEFER, Stance.REJECT, Stance.DECIDE)
