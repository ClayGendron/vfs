"""Tests for path format utilities — chunk refs, version refs, parsing, round-trips."""

from __future__ import annotations

from grover.fs.paths import (
    build_chunk_ref,
    build_version_ref,
    is_chunk_ref,
    is_version_ref,
    parse_ref,
    strip_ref,
)

# ==================================================================
# build_chunk_ref
# ==================================================================


class TestBuildChunkRef:
    def test_simple_symbol(self):
        assert build_chunk_ref("/src/auth.py", "login") == "/src/auth.py#login"

    def test_scoped_symbol(self):
        assert build_chunk_ref("/src/auth.py", "Client.connect") == "/src/auth.py#Client.connect"

    def test_root_file(self):
        assert build_chunk_ref("/main.py", "run") == "/main.py#run"

    def test_deeply_nested(self):
        assert build_chunk_ref("/a/b/c/d.py", "foo") == "/a/b/c/d.py#foo"

    def test_dunder_method(self):
        assert build_chunk_ref("/src/cls.py", "MyClass.__init__") == "/src/cls.py#MyClass.__init__"

    def test_dotted_filename(self):
        assert build_chunk_ref("/src/auth.test.py", "test_login") == "/src/auth.test.py#test_login"


# ==================================================================
# build_version_ref
# ==================================================================


class TestBuildVersionRef:
    def test_simple(self):
        assert build_version_ref("/src/auth.py", 3) == "/src/auth.py@3"

    def test_version_zero(self):
        assert build_version_ref("/src/auth.py", 0) == "/src/auth.py@0"

    def test_large_version(self):
        assert build_version_ref("/file.txt", 999) == "/file.txt@999"


# ==================================================================
# parse_ref
# ==================================================================


class TestParseRef:
    def test_plain_path(self):
        assert parse_ref("/src/auth.py") == ("/src/auth.py", None, None)

    def test_chunk_ref(self):
        assert parse_ref("/src/auth.py#login") == ("/src/auth.py", "login", None)

    def test_scoped_chunk_ref(self):
        assert parse_ref("/src/auth.py#Client.connect") == (
            "/src/auth.py",
            "Client.connect",
            None,
        )

    def test_version_ref(self):
        assert parse_ref("/src/auth.py@3") == ("/src/auth.py", None, 3)

    def test_version_zero(self):
        assert parse_ref("/src/auth.py@0") == ("/src/auth.py", None, 0)

    def test_no_suffix(self):
        base, chunk, ver = parse_ref("/plain/path.txt")
        assert base == "/plain/path.txt"
        assert chunk is None
        assert ver is None

    def test_hash_in_directory_name_with_chunk(self):
        # A # in the middle of a path component with a final # chunk ref
        result = parse_ref("/dir#name/file.py#symbol")
        assert result == ("/dir#name/file.py", "symbol", None)

    def test_hash_in_directory_only(self):
        # A # only in directory — no chunk ref (suffix contains /)
        result = parse_ref("/dir#v1/file.py")
        assert result == ("/dir#v1/file.py", None, None)

    def test_at_in_directory_name(self):
        # A @ in the middle of a path: last @ wins
        result = parse_ref("/dir@v2/file.py@3")
        assert result == ("/dir@v2/file.py", None, 3)

    def test_invalid_version_treated_as_plain(self):
        # @abc is not a valid version number
        assert parse_ref("/file.py@abc") == ("/file.py@abc", None, None)

    def test_empty_chunk_id_treated_as_plain(self):
        # Trailing # with nothing after it
        assert parse_ref("/file.py#") == ("/file.py#", None, None)

    def test_empty_string(self):
        assert parse_ref("") == ("", None, None)

    def test_root_path(self):
        assert parse_ref("/") == ("/", None, None)


# ==================================================================
# Round-trip correctness
# ==================================================================


class TestRoundTrip:
    def test_chunk_round_trip(self):
        """parse_ref(build_chunk_ref(p, c)) == (p, c, None)"""
        path = "/src/auth.py"
        symbol = "login"
        ref = build_chunk_ref(path, symbol)
        base, chunk_id, version = parse_ref(ref)
        assert base == path
        assert chunk_id == symbol
        assert version is None

    def test_version_round_trip(self):
        """parse_ref(build_version_ref(p, v)) == (p, None, v)"""
        path = "/src/auth.py"
        ver = 5
        ref = build_version_ref(path, ver)
        base, chunk_id, version = parse_ref(ref)
        assert base == path
        assert chunk_id is None
        assert version == ver

    def test_strip_chunk_round_trip(self):
        ref = build_chunk_ref("/a/b.py", "func")
        assert strip_ref(ref) == "/a/b.py"

    def test_strip_version_round_trip(self):
        ref = build_version_ref("/a/b.py", 7)
        assert strip_ref(ref) == "/a/b.py"


# ==================================================================
# is_chunk_ref / is_version_ref
# ==================================================================


class TestIsChunkRef:
    def test_true(self):
        assert is_chunk_ref("/a.py#foo") is True

    def test_false_plain(self):
        assert is_chunk_ref("/a.py") is False

    def test_false_version(self):
        assert is_chunk_ref("/a.py@3") is False

    def test_false_trailing_hash(self):
        assert is_chunk_ref("/a.py#") is False

    def test_false_leading_hash(self):
        # hash at position 0 → hash_idx not > 0
        assert is_chunk_ref("#foo") is False

    def test_false_hash_in_directory(self):
        # hash in directory name, suffix contains /
        assert is_chunk_ref("/dir#v1/file.py") is False


class TestIsVersionRef:
    def test_true(self):
        assert is_version_ref("/a.py@3") is True

    def test_false_plain(self):
        assert is_version_ref("/a.py") is False

    def test_false_chunk(self):
        assert is_version_ref("/a.py#foo") is False

    def test_false_non_numeric(self):
        assert is_version_ref("/a.py@abc") is False

    def test_version_zero(self):
        assert is_version_ref("/a.py@0") is True

    def test_false_leading_at(self):
        assert is_version_ref("@3") is False


# ==================================================================
# strip_ref
# ==================================================================


class TestStripRef:
    def test_strip_chunk(self):
        assert strip_ref("/src/auth.py#login") == "/src/auth.py"

    def test_strip_version(self):
        assert strip_ref("/src/auth.py@3") == "/src/auth.py"

    def test_plain_unchanged(self):
        assert strip_ref("/src/auth.py") == "/src/auth.py"

    def test_root(self):
        assert strip_ref("/") == "/"

    def test_empty(self):
        assert strip_ref("") == ""
