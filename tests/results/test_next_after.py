"""``Result.next_after``: the listing key, what each operation on a result does to it, its wire shape and its text."""

from __future__ import annotations

import json

import pytest

from vfs.models import Observation
from vfs.paths import MAX_PATH_LENGTH, Path
from vfs.results import ErrorKind, Result, ResultError, Severity


def page(*paths: str, key: str | None) -> Result:
    rows = [Observation(path=Path(path), kind="file") for path in paths]
    return Result(ops=("ls",), observations=rows, next_after=None if key is None else Path(key))


class TestTheField:
    def test_a_result_has_no_key_by_default(self) -> None:
        assert Result().next_after is None

    def test_the_key_is_a_path(self) -> None:
        assert isinstance(page("/a", key="/a").next_after, Path)


class TestOperations:
    @pytest.mark.parametrize(
        "operation",
        [
            lambda r: r.filter(lambda o: True),
            lambda r: r.sort(key=lambda o: o.path),
            lambda r: r.top(1),
            lambda r: r.kinds("file"),
            lambda r: r.model_copy(),
            lambda r: r._demoted(),
        ],
    )
    def test_enrichment_keeps_the_key(self, operation) -> None:
        assert operation(page("/a", "/b", key="/b")).next_after == "/b"

    @pytest.mark.parametrize(
        "operation",
        [
            lambda a, b: a | b,
            lambda a, b: a & b,
            lambda a, b: a - b,
            lambda a, b: Result.merge([a, b]),
            lambda a, b: Result.merge_branches([a, b]),
        ],
    )
    def test_combining_two_listings_clears_the_key(self, operation) -> None:
        assert operation(page("/a", key="/a"), page("/b", key="/b")).next_after is None

    def test_with_mount_rebases_the_key_and_without_mount_strips_it(self) -> None:
        mounted = page("/a/b", key="/a/b").with_mount("/m")
        assert mounted.next_after == "/m/a/b"
        assert mounted.without_mount("/m").next_after == "/a/b"

    def test_the_root_mount_keeps_the_key(self) -> None:
        assert page("/a", key="/a").with_mount("/").next_after == "/a"

    def test_a_key_that_overflows_its_rebase_ends_the_listing_loudly(self) -> None:
        long = "/" + "/".join(["k" * 200] * 5) + "/" + "k" * (MAX_PATH_LENGTH - 1006)
        mounted = page(long, key=long).with_mount("/m")
        assert mounted.next_after is None
        overflow = [error for error in mounted.errors if error.kind == ErrorKind.unaddressable]
        assert len(overflow) == 1
        assert overflow[0].severity == Severity.warning
        assert overflow[0].data == {"vfs.overflow": {"local_path": long, "next_after": long}}

    def test_a_key_that_names_no_row_on_the_page_overflows_with_its_own_warning(self) -> None:
        long = "/" + "/".join(["k" * 200] * 5) + "/" + "k" * (MAX_PATH_LENGTH - 1006)
        mounted = page("/a", key=long).with_mount("/m")
        assert mounted.next_after is None
        assert [error.data for error in mounted.errors] == [{"vfs.overflow": {"next_after": long}}]


class TestWire:
    @pytest.mark.parametrize("key", ["/big/f00999.txt", '/a dir/it\'s "q".md', "/données/ünï/日本.txt"])
    def test_the_key_round_trips(self, key: str) -> None:
        result = page(key, key=key)
        payload = result.to_payload()
        assert payload["next_after"] == key
        restored = Result.from_payload(json.loads(json.dumps(payload)))
        assert restored.next_after == key
        assert isinstance(restored.next_after, Path)

    def test_an_exhausted_listing_carries_no_key_on_the_wire(self) -> None:
        assert "next_after" not in page("/a", key=None).to_payload()
        assert page("/a", key=None).to_payload(exclude_none=False)["next_after"] is None

    def test_a_peer_without_the_field_round_trips_with_no_key(self) -> None:
        assert Result.from_payload({"success": True, "ops": ["ls"], "observations": []}).next_after is None

    def test_a_malformed_key_quarantines_as_an_envelope_warning(self) -> None:
        restored = Result.from_payload({"ops": ["ls"], "next_after": "/a\x00b"})
        assert restored.next_after is None
        assert restored.success
        assert [error.severity for error in restored.errors] == [Severity.warning]

    def test_rolled_errors_keep_the_key(self) -> None:
        errors = [ResultError(kind=ErrorKind.internal, message="m", source=Path(f"/s{i}")) for i in range(3)]
        result = page("/a", key="/a").model_copy(update={"errors": errors})
        assert result.to_payload(max_errors=1)["next_after"] == "/a"


class TestText:
    def test_a_page_with_a_key_ends_its_body_with_the_more_line(self) -> None:
        text = page("/big/a.txt", key="/big/a.txt").to_str()
        assert text.splitlines()[-1] == "more: after=/big/a.txt"

    def test_the_more_line_comes_before_the_errors(self) -> None:
        warning = ResultError(kind=ErrorKind.internal, message="partial", severity=Severity.warning)
        text = page("/a", key="/a").model_copy(update={"errors": [warning]}).to_str()
        blocks = text.split("\n\n")
        assert blocks[-2] == "more: after=/a"
        assert blocks[-1].startswith("WARNING")

    def test_a_result_with_no_key_has_no_more_line(self) -> None:
        assert "more:" not in page("/a", key=None).to_str()
