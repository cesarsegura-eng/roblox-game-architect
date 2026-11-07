"""Run fixed world-design cases through the configured, budgeted model provider."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

from core.budget import IterationBudget, SpendBudget
from core.evaluation import WORLD_EVALUATION_CASES, WorldEvaluationCase, assess_world_result
from core.llm import FakeProvider, LLMError, LLMProvider, create_provider
from core.worldbuilding import WorldDesignAgent

_FIXTURE_ROOT = Path(__file__).resolve().parents[1] / "examples" / "worlds" / "evaluation"
_FIXTURE_NAMES = {
    "rainforest-checkpoint-obby": "../rainforest-checkpoint-obby/scene-recipe.json",
    "rainforest-trail": "rainforest-trail.json",
    "rainforest-collect-and-win": "../rainforest-checkpoint-obby/scene-recipe.json",
    "desert-courtyard-home": "desert-courtyard-home.json",
    "coastal-wetland": "coastal-wetland.json",
    "alpine-inn": "alpine-inn.json",
    "mangrove-stilt-house": "mangrove-stilt-house.json",
    "guard-walk-cycle": "guard-walk-cycle.json",
}


def _with_fake_fixtures(
    provider: LLMProvider, cases: tuple[WorldEvaluationCase, ...]
) -> tuple[LLMProvider, str]:
    if not isinstance(provider, FakeProvider):
        return provider, "provider_generation"
    responses = {
        case.brief: (_FIXTURE_ROOT / _FIXTURE_NAMES[case.case_id]).read_text(encoding="utf-8")
        for case in cases
    }
    return FakeProvider(responses), "reviewed_fixture_generation"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--case",
        action="append",
        choices=[case.case_id for case in WORLD_EVALUATION_CASES],
        help="run only the selected fixed case (repeat to select multiple)",
    )
    args = parser.parse_args()
    selected_ids = set(args.case or ())
    cases = tuple(
        case for case in WORLD_EVALUATION_CASES if not selected_ids or case.case_id in selected_ids
    )
    try:
        provider, evaluation_mode = _with_fake_fixtures(create_provider(), cases)
        spend = SpendBudget.from_env()
    except (LLMError, OSError, ValueError, RuntimeError) as exc:
        print(f"Evaluation could not start: {exc}", file=sys.stderr)
        return 2

    results = []
    for case in cases:
        try:
            generated = WorldDesignAgent(
                provider,
                iterations=IterationBudget.from_env(),
                spend=spend,
            ).generate(case.brief)
            assessed = assess_world_result(case, generated)
            results.append(
                {
                    "case_id": assessed.case_id,
                    "passed": assessed.passed,
                    "iterations": generated.iterations,
                    "skills": list(generated.skill_names),
                    "checks": [asdict(check) for check in assessed.checks],
                    "recipe": assessed.recipe,
                }
            )
        except Exception as exc:
            results.append(
                {
                    "case_id": case.case_id,
                    "passed": False,
                    "error": str(exc)[:500],
                }
            )

    report = {
        "provider": provider.name,
        "evaluation_mode": evaluation_mode,
        "passed": sum(item["passed"] for item in results),
        "failed": sum(not item["passed"] for item in results),
        "spent_usd": str(spend.spent),
        "scope": (
            "Structural contract and skill coverage only. This does not assess visual "
            "quality, gameplay, Roblox Studio runtime behavior, or production readiness."
        ),
        "results": results,
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
