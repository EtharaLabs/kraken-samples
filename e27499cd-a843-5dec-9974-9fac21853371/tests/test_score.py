"""Unit tests of the reward arithmetic in tests/score.py.

They exercise the per-case and per-family scoring rules against synthetic timings and never
read /logs/verifier, so they run on any host with `python -m pytest tests/test_score.py`. The
verifier image does not carry this file: tests/.dockerignore admits only the files test.sh runs.
"""

from __future__ import annotations

import importlib.util
import math
from pathlib import Path

import pytest

_SPEC = importlib.util.spec_from_file_location(
    "score", Path(__file__).with_name("score.py")
)
assert _SPEC is not None and _SPEC.loader is not None
score = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(score)

BAND = 0.05


def case(base: float, expert: float, patch: float | None) -> dict:
    return {
        "base_median": base,
        "expert_median": expert,
        "patch_median": patch,
        "patch": [patch],
    }


def test_reference_speed_scores_one() -> None:
    assert score.case_score(case(10.0, 1.0, 1.0), BAND) == 1.0


def test_within_noise_band_of_reference_scores_one() -> None:
    assert score.case_score(case(10.0, 1.0, 1.0 * math.exp(BAND / 2)), BAND) == 1.0


def test_no_speedup_scores_zero() -> None:
    assert score.case_score(case(10.0, 1.0, 10.0), BAND) == 0.0


def test_speedup_inside_base_noise_scores_zero() -> None:
    assert score.case_score(case(10.0, 1.0, 10.0 * math.exp(-BAND / 2)), BAND) == 0.0


def test_partial_speedup_is_log_ratio() -> None:
    got = score.case_score(case(100.0, 1.0, 10.0), BAND)
    assert got == pytest.approx(math.log(10.0) / math.log(100.0))


def test_missing_submission_timing_scores_zero() -> None:
    assert score.case_score(case(10.0, 1.0, None), BAND) == 0.0


def test_non_discriminating_case_is_skipped() -> None:
    assert score.case_score(case(1.0, 1.0 * math.exp(-BAND), 1.0), BAND) is None


def test_family_score_is_median_of_informative_cases() -> None:
    slot = {
        "noise_band": BAND,
        "seed": 1,
        "cases": [
            case(100.0, 1.0, 1.0),
            case(100.0, 1.0, 10.0),
            case(100.0, 1.0, 100.0),
        ],
    }
    value, detail = score.family_score(slot)
    assert value == pytest.approx(0.5)
    assert detail["case_scores"] == [1.0, 0.5, 0.0]


def test_family_score_zero_when_a_case_departs_from_base() -> None:
    departed = dict(case(10.0, 1.0, 1.0), patch_diff="moment count differs")
    slot = {"noise_band": BAND, "seed": 1, "cases": [case(10.0, 1.0, 1.0), departed]}
    value, detail = score.family_score(slot)
    assert value == 0.0
    assert "not equivalent" in detail["zero"]


def test_family_score_zero_when_the_submission_run_fails() -> None:
    slot = {
        "noise_band": BAND,
        "seed": 1,
        "cases": [case(10.0, 1.0, 1.0)],
        "patch_failures": 1,
    }
    assert score.family_score(slot)[0] == 0.0
