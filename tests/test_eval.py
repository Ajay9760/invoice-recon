import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "eval"))
import run_eval  # noqa: E402

from app import llm  # noqa: E402

CASES = [json.loads(x) for x in (Path(run_eval.__file__).with_name("cases.jsonl")).read_text().splitlines()]


def test_cases_use_only_allowed_actions():
    assert len(CASES) >= 20 and all(c["expected"] in llm.ALLOWED_ACTIONS for c in CASES)


def test_baseline_scores_and_has_known_misses():
    right, invalid, _, misses = run_eval.run(llm.RuleBasedSuggester(), CASES)
    assert invalid == 0 and 0 < right < len(CASES) and misses   # baseline is imperfect by design
