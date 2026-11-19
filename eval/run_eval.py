"""Score a suggester against hand-labelled cases.

    python eval/run_eval.py                 # rule-based baseline (no API key needed)
    ANTHROPIC_API_KEY=... python eval/run_eval.py --llm

The labels in cases.jsonl are judgement calls: review and relabel them before trusting a score.
Prints overall and per-rule accuracy plus how many replies were invalid (those fall back in the app).
"""
import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import llm  # noqa: E402


def run(suggester, cases):
    right, invalid, per_rule, misses = 0, 0, defaultdict(lambda: [0, 0]), []
    for c in cases:
        try:
            got = suggester.suggest(c["rule_code"], c["severity"], c["detail"]).action
        except llm.SuggestionError:
            got, invalid = None, invalid + 1
        ok = got == c["expected"]
        right += ok
        per_rule[c["rule_code"]][0] += ok
        per_rule[c["rule_code"]][1] += 1
        if not ok:
            misses.append((c, got))
    return right, invalid, per_rule, misses


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--llm", action="store_true", help="use the Anthropic suggester (needs ANTHROPIC_API_KEY)")
    ap.add_argument("--cases", default=str(Path(__file__).with_name("cases.jsonl")))
    args = ap.parse_args()
    cases = [json.loads(line) for line in Path(args.cases).read_text().splitlines() if line.strip()]
    suggester = llm.AnthropicSuggester() if args.llm else llm.RuleBasedSuggester()
    right, invalid, per_rule, misses = run(suggester, cases)
    print(f"{type(suggester).__name__}: {right}/{len(cases)} correct ({right / len(cases):.0%}), {invalid} invalid replies")
    for rule, (r, n) in sorted(per_rule.items()):
        print(f"  {rule:<24}{r}/{n}")
    for c, got in misses:
        print(f"  MISS {c['rule_code']}: expected {c['expected']}, got {got} | {c['detail'][:70]}")


if __name__ == "__main__":
    main()
