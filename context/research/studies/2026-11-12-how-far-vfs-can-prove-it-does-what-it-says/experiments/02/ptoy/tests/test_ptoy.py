from ptoy import chunk_lengths, may_read, membership_budget


def test_budget_takes_a_cap():
    assert membership_budget(1000, 2100) <= 1000


def test_budget_zero():
    assert membership_budget(0, 5) == 1


def test_chunks_cover():
    assert sum(chunk_lengths(2500, 1000)) == 2500


def test_grant_on_self():
    assert may_read(["/a"], "/a")


def test_grant_on_parent():
    assert may_read(["/a"], "/a/b")
