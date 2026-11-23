import json

import pytest
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


def test_llm_flag_without_a_key_fails_instead_of_scoring_the_baseline(monkeypatch):
    for v in ("ANTHROPIC_API_KEY", "GEMINI_API_KEY", "LLM_PROVIDER"):
        monkeypatch.delenv(v, raising=False)
    monkeypatch.setattr(sys, "argv", ["run_eval.py", "--llm"])
    with pytest.raises(SystemExit) as exc:
        run_eval.main()
    assert "THIS terminal" in str(exc.value)


def test_hard_cases_are_valid_and_actually_discriminating():
    hard = [json.loads(x) for x in Path(run_eval.__file__).with_name("cases_hard.jsonl").read_text().splitlines()]
    assert len(hard) == 15 and all(c["expected"] in llm.ALLOWED_ACTIONS for c in hard)
    right, invalid, _, _ = run_eval.run(llm.RuleBasedSuggester(), hard)
    assert invalid == 0 and right <= 10   # the baseline must lose at least 5, or the set proves nothing
