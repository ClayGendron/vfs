from hypothesis import given
from hypothesis import strategies as st

from ptoy import chunk_lengths, may_read, membership_budget

caps = st.integers(min_value=0, max_value=5000)


@given(caps, caps)
def test_budget_is_the_tighter_cap(a, b):
    assert membership_budget(a, b) == max(1, min(a, b))


@given(st.integers(min_value=0, max_value=20000), st.integers(min_value=1, max_value=3000))
def test_chunks_are_bounded_and_exact(n, size):
    lengths = chunk_lengths(n, size)
    assert sum(lengths) == n
    assert all(0 < x <= size for x in lengths)
    assert len(lengths) == -(-n // size)


segment = st.text(alphabet="ab", min_size=1, max_size=3)


@given(segment, segment)
def test_no_grant_reaches_a_sibling_prefix(g, extra):
    assert not may_read(["/" + g], "/" + g + extra)
