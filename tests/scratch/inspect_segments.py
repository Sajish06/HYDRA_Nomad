import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from app.analysis.cues import detect_cues, detect_primary_cue
from tests.test_user_benchmark import BENCHMARK_DATA

for m in BENCHMARK_DATA:
    print(f"\n=== {m['meeting_id']}: {m['title']} ===")
    for s in m['segments']:
        p = detect_primary_cue(s['text'])
        st = p['stance'].value if p else 'INFORM'
        print(f"[{s['idx']:02d}] {s['speaker']:<7}: {s['text']:<75} -> {st}")
