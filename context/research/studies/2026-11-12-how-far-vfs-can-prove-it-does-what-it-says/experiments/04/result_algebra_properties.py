"""Experiment 04-c: the Result algebra laws, stated once and searched by Hypothesis.

Run from the checkout root, with Hypothesis's store outside it:
HYPOTHESIS_STORAGE_DIRECTORY=<scratch>/hyp uv run --with hypothesis pytest <this file> -p no:cacheprovider --no-cov -n 0 -q
The suite pins each law on one hand-built example (tests/results/test_result_laws.py).
Here each law is a property over generated envelopes: rows drawn from a small path
alphabet with optional scores and sizes, errors from the whole kind vocabulary.
"""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from vfs.models import Observation
from vfs.results import ErrorKind, Result, ResultError

PATHS = ("/a.md", "/b.md", "/d/c.md", "/d/e/f.md")
OPS = ("glob", "grep", "ls", "read", "search")

observations = st.builds(
    lambda path, score, size: Observation.model_validate(
        {"path": path, **({"score": score} if score is not None else {}), **({"size_bytes": size} if size is not None else {})}
    ),
    st.sampled_from(PATHS),
    st.none() | st.floats(min_value=0, max_value=1, allow_nan=False),
    st.none() | st.integers(min_value=0, max_value=10_000),
)
errors = st.builds(
    lambda kind, message: ResultError.model_validate({"kind": kind, "message": message}),
    st.sampled_from(list(ErrorKind)),
    st.sampled_from(("a down", "gone", "slow")),
)
results = st.builds(
    lambda ops, rows, errs: Result(ops=ops, observations=rows, errors=errs),
    st.lists(st.sampled_from(OPS), min_size=1, max_size=2, unique=True).map(tuple),
    st.lists(observations, max_size=4),
    st.lists(errors, max_size=2),
)


@settings(max_examples=2_000, deadline=None, database=None)
@given(results, results, results)
def test_union_is_associative(a: Result, b: Result, c: Result) -> None:
    assert (a | b) | c == a | (b | c)


@settings(max_examples=2_000, deadline=None, database=None)
@given(results)
def test_empty_result_is_the_identity(a: Result) -> None:
    assert a | Result() == a
    assert Result() | a == a


@settings(max_examples=2_000, deadline=None, database=None)
@given(results, results)
def test_success_is_a_homomorphism(a: Result, b: Result) -> None:
    assert (a | b).success == (a.success and b.success)


@settings(max_examples=2_000, deadline=None, database=None)
@given(results)
def test_wire_round_trip_preserves_value(a: Result) -> None:
    assert Result.from_payload(a.to_payload()) == a
