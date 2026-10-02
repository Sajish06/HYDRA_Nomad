import pytest
from app.analysis.stance import validate_quote

def test_exact_quote_grounding():
    seg_text = "Let's definitely create dedicated teams for both."
    quote = "definitely create dedicated teams"
    
    val_q, repaired = validate_quote(quote, seg_text)
    assert not repaired
    assert val_q.lower() == quote.lower()
    assert val_q in seg_text

def test_hallucinated_quote_repaired():
    seg_text = "Let's definitely create dedicated teams for both."
    hallucinated_quote = "We decided we will form teams"
    
    val_q, repaired = validate_quote(hallucinated_quote, seg_text)
    assert repaired
    assert val_q == seg_text
