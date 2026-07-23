"""Tests for vfs.paths — the path gate, Path, and the pure helpers it composes.

Self-contained: imports only from ``vfs.paths`` (no backends, models, or fixtures)
so it collects and runs while the rest of the tree is mid-refactor.
"""

from __future__ import annotations

import posixpath
import time
from typing import cast

import pytest
from pydantic import BaseModel, ValidationError

from vfs.paths import (
    MAX_PATH_LENGTH,
    MAX_SEGMENT_LENGTH,
    METADATA_ROOT,
    Path,
    RelativePath,
    ResolvedPath,
    ResolvedRelativePath,
    check_mutable_path,
    compute_parent_dir,
    extract_extension,
    is_meta_path,
    is_reserved_directory,
    normalize_path,
    normalize_relative_path,
    parse_kind,
    resolve_path,
    resolve_relative_path,
    skill_manifest_path,
    skill_path,
    split_path,
    tool_manifest_path,
    tool_path,
    validate_path,
    validate_relative_path,
    validate_segment,
)

# =========================================================================
# normalize_path
# =========================================================================


class TestNormalizePath:
    def test_empty_string(self):
        assert normalize_path("") == "/"

    def test_adds_leading_slash(self):
        assert normalize_path("foo.txt") == "/foo.txt"

    def test_resolves_double_slashes(self):
        assert normalize_path("/foo//bar.txt") == "/foo/bar.txt"

    def test_resolves_dot_dot(self):
        assert normalize_path("/foo/../bar.txt") == "/bar.txt"

    def test_resolves_single_dot(self):
        assert normalize_path("/foo/./bar.txt") == "/foo/bar.txt"

    def test_removes_trailing_slash(self):
        assert normalize_path("/foo/") == "/foo"

    def test_root_preserved(self):
        assert normalize_path("/") == "/"

    def test_idempotent(self):
        once = normalize_path("/foo/../bar//baz/")
        assert normalize_path(once) == once

    def test_dot_dot_at_root_clamps(self):
        assert normalize_path("/../../../etc/passwd") == "/etc/passwd"

    def test_metadata_traversal(self):
        assert normalize_path("/.vfs/../../../etc/passwd") == "/etc/passwd"

    def test_nfc_normalization(self):
        # NFD é (e + combining acute) should collapse to NFC é
        nfd = "/café"
        nfc = "/café"
        assert normalize_path(nfd) == normalize_path(nfc)

    def test_whitespace_stripped(self):
        assert normalize_path("  /foo  ") == "/foo"

    def test_only_slashes(self):
        assert normalize_path("///") == "/"

    def test_double_leading_slash_collapses_to_single_rooted_path(self):
        assert normalize_path("//src/auth.py") == "/src/auth.py"

    def test_trailing_whitespace_segment_after_collapse(self):
        # normpath can expose a trailing-space segment; the result must still be canonical.
        assert normalize_path("/a //") == "/a"

    def test_whitespace_padded_navigational_segments_collapse(self):
        # ". " is not navigational to normpath, but stripping it reveals "." — the
        # canonical form must fully collapse it, not stop one step short.
        assert normalize_path(". /") == "/"
        assert normalize_path("/foo/" + chr(0x2009) + "/") == "/foo"
        assert normalize_path(".." + chr(0x3000) + "//") == "/"

    @pytest.mark.parametrize(
        "raw",
        [
            "/a //",
            "/x/leaf //",
            "/ /",
            "/a /.",
            ". /",
            "/foo/" + chr(0x2009) + "/",
            ".." + chr(0x3000) + "//",
            "/a/./ /../b",
        ],
    )
    def test_idempotent_after_whitespace_collapse(self, raw):
        once = normalize_path(raw)
        assert normalize_path(once) == once

    def test_interior_whitespace_only_segment_collapses(self):
        # A whitespace-only segment is dropped uniformly, interior or trailing.
        assert normalize_path("/a/ /b") == "/a/b"
        assert normalize_path("/a/" + chr(0x00A0) + "/b") == "/a/b"
        assert normalize_path("/a/b/ ") == "/a/b"

    def test_normalize_is_linear(self):
        # Regression guard: a pathological "/. " repetition must not be O(n^2).
        big = "/a" + "/. " * 100000
        start = time.perf_counter()
        assert normalize_path(big) == "/a"
        assert time.perf_counter() - start < 1.0


# =========================================================================
# split_path
# =========================================================================


class TestSplitPath:
    def test_root(self):
        assert split_path(Path("/")) == ("/", "")

    def test_single_segment(self):
        assert split_path(Path("/foo")) == ("/", "foo")

    def test_nested(self):
        assert split_path(Path("/src/auth.py")) == ("/src", "auth.py")

    def test_meta_scope_path_is_literal_split(self):
        # split_path is a pure string operation, scope-unaware.
        assert split_path(Path("/.vfs/trash/2026-07-18-10/x.txt")) == (
            "/.vfs/trash/2026-07-18-10",
            "x.txt",
        )


# =========================================================================
# validate_path
# =========================================================================


class TestValidatePath:
    def test_valid_paths(self):
        valid = [
            "/src/auth.py",
            "/",
            "/a",
            "/.vfs/trash/2026-07-18-10/x.txt",
            "/documents/quarterly-report.pdf",
        ]
        for p in valid:
            ok, msg = validate_path(p)
            assert ok, f"{p!r} should be valid: {msg}"

    def test_null_byte(self):
        ok, _ = validate_path("/foo\x00bar")
        assert not ok

    @pytest.mark.parametrize(
        "ch",
        ["\x01", "\x0b", "\x1f", "\t", "\n", "\r"],
        ids=["SOH", "VT", "US", "tab", "newline", "CR"],
    )
    def test_ascii_control_chars_rejected(self, ch):
        ok, _ = validate_path(f"/foo{ch}bar")
        assert not ok

    def test_del_rejected(self):
        ok, _ = validate_path("/foo\x7fbar")
        assert not ok

    def test_c1_control_rejected(self):
        ok, _ = validate_path("/foo\x9fbar")
        assert not ok

    def test_path_too_long(self):
        ok, _ = validate_path("/" + "a" * 1024)
        assert not ok

    def test_path_at_limit(self):
        # 1024 total: "/" + 4 segments of "a" * 255 joined by "/"
        # = 1 + 1020 + 3 = 1024
        path = "/" + "/".join(["a" * 255] * 4)
        assert len(path) <= 1024
        ok, _ = validate_path(path)
        assert ok

    def test_segment_too_long(self):
        ok, _ = validate_path("/" + "a" * 256)
        assert not ok

    def test_segment_at_limit(self):
        ok, _ = validate_path("/" + "a" * 255)
        assert ok

    def test_root_accepted(self):
        ok, _ = validate_path("/")
        assert ok

    def test_meta_scope_paths_take_the_ordinary_grammar(self):
        # No per-file metadata grammar remains: any structurally-sound shape
        # under /.vfs is a lawful path, __meta__ included as a plain name.
        for p in ("/.vfs/anything/at/all", "/.vfs/__meta__", "/a/__meta__/b/__meta__/c"):
            ok, msg = validate_path(p)
            assert ok, f"{p!r} should be valid: {msg}"


# =========================================================================
# validate_segment
# =========================================================================


class TestValidateSegment:
    def test_valid_segment_returns_itself(self):
        assert validate_segment("imports", "edge_type") == "imports"

    @pytest.mark.parametrize("bad", ["", "   ", "a/b", ".", ".."])
    def test_empty_slash_and_traversal_rejected(self, bad):
        with pytest.raises(ValueError, match="label"):
            validate_segment(bad, "label")

    @pytest.mark.parametrize("bad", ["a\x00b", "a\nb", "a\x7fb", "bad‮", "a﻿b", "a" + chr(0xD800) + "b"])
    def test_gate_rejected_characters_rejected(self, bad):
        with pytest.raises(ValueError, match="label"):
            validate_segment(bad, "label")


# =========================================================================
# check_mutable_path
# =========================================================================


class TestCheckMutablePath:
    def test_root_is_not_mutable(self):
        assert check_mutable_path(Path("/")) == (False, "Cannot mutate root path")

    def test_reserved_metadata_root_is_not_mutable(self):
        assert check_mutable_path(Path(METADATA_ROOT)) == (False, "Cannot mutate reserved metadata root '/.vfs'")

    def test_non_metadata_paths_are_mutable(self):
        assert check_mutable_path(Path("/src/auth.py")) == (True, "")

    def test_meta_scope_paths_are_mutable(self):
        # Trash-side writes are ordinary writes: the meta scope hides rows
        # from default enumeration; it does not refuse mutation.
        assert check_mutable_path(Path("/.vfs/trash/2026-07-18-10/x.txt")) == (True, "")
        assert check_mutable_path(Path("/.vfs/trash")) == (True, "")


# =========================================================================
# resolve_path  (the gate)
# =========================================================================


class TestResolvePath:
    def test_valid_returns_canonical_vfspath(self):
        result = resolve_path("/src/auth.py")
        assert result == ResolvedPath(Path("/src/auth.py"), None)
        assert result.error is None
        assert isinstance(result.path, Path)

    def test_canonicalizes_rather_than_rejecting(self):
        # The gate normalizes; it does not reject non-canonical input.
        assert resolve_path("/a/../b").path == "/b"
        assert resolve_path("rel").path == "/rel"

    def test_invalid_returns_reason_and_no_path(self):
        result = resolve_path("/a\x00b")
        assert result.path is None
        assert result.error

    def test_mutation_applies_check_mutable_path(self):
        assert resolve_path("/", mutation=True).path is None
        # error mirrors check_mutable_path's reason
        assert resolve_path("/", mutation=True).error == "Cannot mutate root path"

    def test_mutation_allows_ordinary_path(self):
        assert resolve_path("/src/auth.py", mutation=True).path == "/src/auth.py"

    def test_never_raises(self):
        # A hostile / structurally invalid path returns a reason, never raises.
        for bad in ["/a\x00b", "/" + "a" * 2000, "/x\x01y"]:
            result = resolve_path(bad)
            assert result.path is None
            assert result.error

    def test_branded_input_passes_through_unchanged(self):
        # Idempotent gate: a Path carries its proof, so it returns as-is.
        p = Path("/src/auth.py")
        result = resolve_path(p)
        assert result.path is p
        assert result.error is None

    def test_branded_input_still_runs_mutation_check(self):
        # The one thing construction does not prove: mutation authorization.
        assert resolve_path(Path("/"), mutation=True).path is None
        assert resolve_path(Path("/"), mutation=True).error == "Cannot mutate root path"
        assert resolve_path(Path("/src/auth.py"), mutation=True).path == "/src/auth.py"

    def test_path_constructor_is_identity_on_branded_input(self):
        p = Path("/src/auth.py")
        assert Path(p) is p


# =========================================================================
# Path
# =========================================================================


class TestPath:
    def test_is_a_str(self):
        p = Path("/a/b")
        assert p == "/a/b"
        assert isinstance(p, str)

    def test_canonicalizes_without_raising(self):
        assert Path("/a/../b") == "/b"
        assert Path("rel") == "/rel"

    def test_raises_on_null_byte(self):
        with pytest.raises(ValueError):
            Path("/a\x00b")

    def test_raises_on_control_char(self):
        with pytest.raises(ValueError):
            Path("/a\x01b")

    def test_raises_on_overlong_segment(self):
        with pytest.raises(ValueError):
            Path("/" + "a" * 256)

    def test_raises_on_overlong_path(self):
        with pytest.raises(ValueError):
            Path("/" + "a" * 1025)

    def test_derived_strings_drop_the_badge(self):
        p = Path("/a/b")
        assert type(p[1:]) is str
        assert type(p + "x") is str
        assert type(p.lstrip("/")) is str

    def test_no_infinite_recursion_on_construction(self):
        # __new__ delegates to resolve_path, which brands via str.__new__ — not Path(...).
        assert Path(Path("/a/b")) == "/a/b"

    # --- properties mirror the paths.py helpers on the same input ---

    @pytest.mark.parametrize(
        "path",
        [
            "/src/auth.py",
            "/src",
            "/.vfs/trash/2026-07-18-10/x.txt",
            "/.agents/tools/clone-repo",
        ],
    )
    def test_parent_dir_matches_helper(self, path):
        assert Path(path).parent_dir == compute_parent_dir(path)

    @pytest.mark.parametrize(
        "path,name",
        [("/src/auth.py", "auth.py"), ("/", ""), ("/a", "a")],
    )
    def test_name_matches_helper(self, path, name):
        assert Path(path).name == split_path(path)[1] == name

    @pytest.mark.parametrize(
        "path",
        [
            "/src/auth.py",
            "/src",
            "/.vfs/trash/2026-07-18-10/x.txt",
            "/.agents/skills/pdf-processing",
        ],
    )
    def test_kind_matches_helper(self, path):
        assert Path(path).kind == parse_kind(path)

    @pytest.mark.parametrize(
        "path,ext",
        [
            ("/src/auth.py", "py"),
            ("/src/Foo.PY", "py"),  # lowercased
            ("/Makefile", None),  # extensionless file
            ("/.env", None),  # dotfile
            ("/src", None),  # no dotted leaf
            ("/a/foo.bar", "bar"),  # dotted leaf carries ext for any kind
            ("/.vfs/trash/2026-07-18-10/x.txt", "txt"),  # meta scope, ordinary rules
        ],
    )
    def test_ext_derives_from_the_path_never_the_kind(self, path, ext):
        assert Path(path).ext == ext

    @pytest.mark.parametrize(
        "path,expected",
        [("/src/auth.py", False), ("/.vfs/src/auth.py", True), ("/.vfs", True)],
    )
    def test_is_meta_matches_helper(self, path, expected):
        assert Path(path).is_meta is is_meta_path(path) is expected

    @pytest.mark.parametrize(
        "path",
        [
            "/src/auth.py",
            "/",
            "/.vfs",
            "/.vfs/trash/2026-07-18-10/x.txt",
        ],
    )
    def test_is_mutable_target_matches_helper(self, path):
        assert Path(path).is_mutable_target == check_mutable_path(Path(path))[0]

    def test_joinpath_canonicalizes(self):
        assert Path("/a").joinpath("b", "c") == "/a/b/c"

    def test_joinpath_collapses_dotdot(self):
        assert Path("/a/b").joinpath("..", "c") == "/a/c"

    def test_joinpath_absolute_segment_resets(self):
        assert Path("/a/b").joinpath("/c") == "/c"

    def test_joinpath_returns_vfspath(self):
        assert isinstance(Path("/a").joinpath("b"), Path)

    def test_truediv_joins_single_segment(self):
        result = Path("/a") / "b"
        assert result == "/a/b"
        assert isinstance(result, Path)

    def test_str_join_is_not_shadowed(self):
        # ``join`` keeps separator semantics: Path is the separator here.
        assert Path("/").join(["a", "b"]) == "a/b"

    def test_pydantic_field_validates_coerces_and_serializes(self):
        class M(BaseModel):
            p: Path

        # A plain str is coerced through the gate (canonicalized) into a Path.
        m = M(p="/a/../b")
        assert isinstance(m.p, Path)
        assert m.p == "/b"
        # Serializes back to a plain str.
        assert m.model_dump() == {"p": "/b"}

    def test_pydantic_field_rejects_invalid_path(self):
        class M(BaseModel):
            p: Path

        with pytest.raises(ValidationError):
            M(p="/a\x00b")


# =========================================================================
# Path.with_mount / without_mount  (routing rebase)
# =========================================================================


class TestPathMount:
    # --- with_mount: local -> global ---

    def test_with_mount_simple(self):
        assert Path("/bar.py").with_mount("/mnt/foo") == "/mnt/foo/bar.py"

    def test_with_mount_nested(self):
        assert Path("/a/b/c").with_mount("/mnt") == "/mnt/a/b/c"

    def test_with_mount_root_local_maps_to_mount(self):
        assert Path("/").with_mount("/mnt/foo") == "/mnt/foo"

    def test_with_mount_root_mount_is_identity(self):
        assert Path("/bar.py").with_mount("/") == "/bar.py"

    def test_with_mount_empty_mount_is_identity(self):
        # "" canonicalizes to "/", so an empty mount is the root identity.
        assert Path("/bar.py").with_mount("") == "/bar.py"

    def test_with_mount_returns_vfspath(self):
        assert isinstance(Path("/bar.py").with_mount("/mnt"), Path)

    # --- without_mount: global -> local ---

    def test_without_mount_simple(self):
        assert Path("/mnt/foo/bar.py").without_mount("/mnt/foo") == "/bar.py"

    def test_without_mount_nested(self):
        assert Path("/mnt/a/b/c").without_mount("/mnt") == "/a/b/c"

    def test_without_mount_exact_match_collapses_to_root(self):
        assert Path("/mnt/foo").without_mount("/mnt/foo") == "/"

    def test_without_mount_root_mount_is_identity(self):
        assert Path("/mnt/foo/bar.py").without_mount("/") == "/mnt/foo/bar.py"

    def test_without_mount_returns_vfspath(self):
        assert isinstance(Path("/mnt/foo/bar.py").without_mount("/mnt"), Path)

    @pytest.mark.parametrize(
        ("path", "mount"),
        [
            ("/mnt/foobar/x", "/mnt/foo"),  # sibling sharing a name prefix
            ("/ab", "/a"),  # one-level non-boundary prefix
            ("/a/bc/d", "/a/b"),  # deeper non-boundary prefix
            ("/other/x", "/mnt/foo"),  # unrelated subtree
            ("/mnt/fo", "/mnt/foo"),  # mount longer than path
        ],
    )
    def test_without_mount_rejects_non_boundary_prefix(self, path, mount):
        with pytest.raises(ValueError, match="is not within mount"):
            Path(path).without_mount(mount)

    # --- mount canonicalization: all forms behave identically ---

    @pytest.mark.parametrize(
        "mount",
        ["/mnt/foo", "/mnt/foo/", "mnt/foo", "//mnt//foo", "/mnt/x/../foo", "/mnt/./foo"],
    )
    def test_with_mount_canonicalizes_mount(self, mount):
        assert Path("/bar.py").with_mount(mount) == "/mnt/foo/bar.py"

    @pytest.mark.parametrize(
        "mount",
        ["/mnt/foo", "/mnt/foo/", "mnt/foo", "//mnt//foo", "/mnt/x/../foo", "/mnt/./foo"],
    )
    def test_without_mount_canonicalizes_mount(self, mount):
        assert Path("/mnt/foo/bar.py").without_mount(mount) == "/bar.py"

    @pytest.mark.parametrize(
        "mount",
        ["/", "/x/..", "/../..", ""],
    )
    def test_mounts_that_canonicalize_to_root_are_identity(self, mount):
        p = Path("/mnt/foo/bar.py")
        assert p.with_mount(mount) == p
        assert p.without_mount(mount) == p

    # --- round-trip invariant: with_mount then without_mount is identity ---

    @pytest.mark.parametrize(
        "path",
        [
            "/bar.py",
            "/",
            "/a/b/c",
            "/.vfs/trash/2026-07-18-10/x.txt",
            "/Makefile",
        ],
    )
    @pytest.mark.parametrize("mount", ["/mnt", "/mnt/foo", "/deep/mount/point"])
    def test_roundtrip_with_then_without(self, path, mount):
        p = Path(path)
        assert p.with_mount(mount).without_mount(mount) == p

    def test_roundtrip_without_then_with(self):
        # Exact-match path collapses to "/" then re-expands to the mount.
        p = Path("/mnt/foo")
        assert p.without_mount("/mnt/foo").with_mount("/mnt/foo") == p

    # --- invalid mount argument raises a clean ValueError ---

    @pytest.mark.parametrize("mount", [123, None, b"/mnt", ["/mnt"], "/m\x00nt"])
    def test_with_mount_invalid_mount_raises_valueerror(self, mount):
        with pytest.raises(ValueError):
            Path("/bar.py").with_mount(mount)

    @pytest.mark.parametrize("mount", [123, None, b"/mnt", ["/mnt"], "/m\x00nt"])
    def test_without_mount_invalid_mount_raises_valueerror(self, mount):
        with pytest.raises(ValueError):
            Path("/mnt/foo/bar.py").without_mount(mount)


# =========================================================================
# Rebase length policy — 1024 is a hard, namespace-wide invariant
# =========================================================================

# A valid 1004-char local path: "/" + four 250-char segments joined by "/".
DEEP_LOCAL = "/" + "/".join(["a" * 250] * 4)


class TestRebaseLengthPolicy:
    def test_named_limits(self):
        assert MAX_PATH_LENGTH == 1024
        assert MAX_SEGMENT_LENGTH == 255

    def test_validators_name_the_limits(self):
        ok, reason = validate_path("/" + "a" * MAX_PATH_LENGTH)
        assert not ok and str(MAX_PATH_LENGTH) in reason
        ok, reason = validate_path("/" + "a" * (MAX_SEGMENT_LENGTH + 1))
        assert not ok and str(MAX_SEGMENT_LENGTH) in reason

    def test_limits_denominate_utf8_bytes_not_characters(self):
        # "é" is 2 UTF-8 bytes: 128 of them fit a 255-byte segment where
        # 128 ASCII pairs would; the same name at 512 chars is 1,024 bytes
        # and overflows the whole-path limit despite being under it in chars.
        ok, _ = validate_path("/" + "é" * 127)
        assert ok
        ok, reason = validate_path("/" + "é" * 128)
        assert not ok and "bytes" in reason
        long_multibyte = "/" + "/".join(["é" * 120] * 5)  # 1,205 bytes, 605 chars
        ok, reason = validate_path(long_multibyte)
        assert not ok and "bytes" in reason

    def test_with_mount_measures_bytes(self):
        # A 22-byte mount + a 1,004-byte multibyte local path > 1,024 bytes,
        # though the char count (504 + 22) is far under the limit.
        local = "/" + "/".join(["é" * 125] * 4)  # 504 chars, 1,004 bytes
        with pytest.raises(ValueError, match="Rebased path too long"):
            Path(local).with_mount("/" + "m" * 21)

    def test_with_mount_at_exactly_the_limit_passes(self):
        mount = "/" + "m" * 19  # 20 + 1004 == 1024
        rebased = Path(DEEP_LOCAL).with_mount(mount)
        assert len(rebased) == MAX_PATH_LENGTH
        assert isinstance(rebased, Path)

    def test_with_mount_one_past_the_limit_raises_naming_lengths(self):
        mount = "/" + "m" * 20  # 21 + 1004 == 1025
        with pytest.raises(ValueError, match="Rebased path too long") as exc:
            Path(DEEP_LOCAL).with_mount(mount)
        assert str(MAX_PATH_LENGTH) in str(exc.value)
        assert str(len(DEEP_LOCAL)) in str(exc.value)

    def test_without_mount_strips_a_max_length_path(self):
        # Stripping only shortens, so the inbound half has no length guard.
        mount = "/" + "m" * 19
        global_path = Path(DEEP_LOCAL).with_mount(mount)
        local = global_path.without_mount(mount)
        assert local == DEEP_LOCAL
        assert isinstance(local, Path)

    # --- brand-equivalence: the fast path agrees with the full gate ---

    @pytest.mark.parametrize(
        "path",
        ["/", "/bar.py", "/a/b/c", "/Makefile", "/.vfs/trash/2026-07-18-10/x.txt"],
    )
    @pytest.mark.parametrize("mount", ["/", "/mnt", "/mnt/foo", "/deep/mount/point"])
    def test_with_mount_matches_gate_construction(self, path, mount):
        got = Path(path).with_mount(mount)
        assert got == Path(posixpath.join(mount, path[1:]))
        assert isinstance(got, Path)
        # branded output passes the gate unchanged (re-addressable)
        assert resolve_path(got).path is got

    @pytest.mark.parametrize(
        "path",
        ["/", "/bar.py", "/a/b/c", "/Makefile", "/.vfs/trash/2026-07-18-10/x.txt"],
    )
    @pytest.mark.parametrize("mount", ["/", "/mnt", "/mnt/foo", "/deep/mount/point"])
    def test_rebase_inverse_law(self, path, mount):
        p = Path(path)
        assert p.with_mount(mount).without_mount(mount) == p
        q = p.with_mount(mount)
        assert q.without_mount(mount).with_mount(mount) == q


# =========================================================================
# parse_kind
# =========================================================================


class TestParseKind:
    # --- Files with extensions ---

    @pytest.mark.parametrize("path", ["/src/auth.py", "/docs/readme.md", "/data/report.pdf"])
    def test_file_with_extension(self, path):
        assert parse_kind(path) == "file"

    def test_multiple_extensions(self):
        assert parse_kind(Path("/archive.tar.gz")) == "file"

    def test_trailing_dot(self):
        # file. has a dot at position > 0
        assert parse_kind(Path("/file.")) == "file"

    def test_root_is_a_directory(self):
        assert parse_kind(Path("/")) == "directory"

    def test_degenerate_empty_name_fails_safe_to_directory(self):
        # Out-of-contract input: not reserved, splits to an empty leaf —
        # the guard classifies directory instead of joining the lottery.
        assert parse_kind(cast("Path", "")) == "directory"

    # --- Dotfiles ---

    @pytest.mark.parametrize("name", [".bashrc", ".gitconfig", ".hidden", ".vimrc"])
    def test_unlisted_dotfiles_are_files(self, name):
        assert parse_kind(Path(f"/home/{name}")) == "file"

    def test_listed_dotfile(self):
        assert parse_kind(Path("/.gitignore")) == "file"

    def test_dotfile_with_extension(self):
        assert parse_kind(Path("/.env.local")) == "file"

    @pytest.mark.parametrize("name", [".chunks", ".versions", ".connections"])
    def test_dot_prefixed_metadata_like_names_are_files(self, name):
        assert parse_kind(Path(f"/foo/{name}")) == "file"

    # --- Extensionless files (case-insensitive) ---

    @pytest.mark.parametrize("name", ["Makefile", "makefile", "MAKEFILE"])
    def test_makefile_case_insensitive(self, name):
        assert parse_kind(Path(f"/{name}")) == "file"

    @pytest.mark.parametrize("name", ["LICENSE", "license", "License"])
    def test_license_case_insensitive(self, name):
        assert parse_kind(Path(f"/{name}")) == "file"

    def test_dockerfile(self):
        assert parse_kind(Path("/Dockerfile")) == "file"

    # --- Directories ---

    @pytest.mark.parametrize("path", ["/src", "/documents", "/", "/people/teams"])
    def test_directories(self, path):
        assert parse_kind(path) == "directory"

    def test_similar_name_not_misclassified(self):
        assert parse_kind(Path("/my-connections/file.sql")) == "file"

    # --- The meta scope takes the ordinary rules; only its root is structural ---

    def test_metadata_root_is_classified_as_directory(self):
        # ".vfs" is a dotted leaf — without the structural pin it would read
        # as a file through the name lottery.
        assert parse_kind(Path(METADATA_ROOT)) == "directory"

    @pytest.mark.parametrize(
        "path,kind",
        [
            ("/.vfs/trash", "directory"),
            ("/.vfs/trash/2026-07-18-10", "directory"),
            ("/.vfs/trash/2026-07-18-10/x.txt", "file"),
            ("/.vfs/src/auth.py", "file"),
        ],
    )
    def test_meta_scope_paths_take_the_ordinary_rules(self, path, kind):
        assert parse_kind(Path(path)) == kind

    def test_meta_marker_names_are_ordinary_segments(self):
        # The retired grammar's marker is just a name now, anywhere.
        assert parse_kind(Path("/foo/__meta__")) == "directory"
        assert parse_kind(Path("/foo/__meta__/login.txt")) == "file"


# =========================================================================
# is_reserved_directory — the structural-spot predicate
# =========================================================================


class TestIsReservedDirectory:
    @pytest.mark.parametrize(
        "path",
        [
            "/",
            "/.vfs",
            "/.agents",
            "/.agents/tools",
            "/.agents/skills",
            "/.agents/tools/clone-repo",
            "/.agents/skills/pdf-processing",
        ],
    )
    def test_structural_spots(self, path):
        assert is_reserved_directory(Path(path)) is True

    @pytest.mark.parametrize(
        "path",
        [
            "/src",
            "/.vfs/trash",
            "/.agents/memories",  # unknown family
            "/.agents/tools/clone-repo/scripts",  # deeper than the unit
            "/.agents-archive/tools/x",  # lookalike root
        ],
    )
    def test_ordinary_spots(self, path):
        assert is_reserved_directory(Path(path)) is False


# =========================================================================
# Agent namespace (/.agents tools + skills)
# =========================================================================


class TestAgentNamespace:
    # --- parse_kind: units are plain directories, discovered by path ---

    def test_tool_unit_is_a_directory(self):
        assert parse_kind(Path("/.agents/tools/clone-repo")) == "directory"

    def test_skill_unit_is_a_directory(self):
        assert parse_kind(Path("/.agents/skills/pdf-processing")) == "directory"

    def test_agents_root_is_a_directory(self):
        # Its dotfile leaf would otherwise read as a file.
        assert parse_kind(Path("/.agents")) == "directory"

    @pytest.mark.parametrize("path", ["/.agents/tools", "/.agents/skills"])
    def test_family_roots_are_directories(self, path):
        assert parse_kind(path) == "directory"

    def test_dotted_unit_name_stays_a_directory(self):
        # The structural pin keeps a dotted unit name out of the name lottery.
        assert parse_kind(Path("/.agents/tools/clone.repo")) == "directory"

    def test_tool_manifest_is_a_plain_indexable_file(self):
        # The manifest is a file, not the unit — so it chunks/indexes like any file.
        assert parse_kind(Path("/.agents/tools/clone-repo/TOOL.md")) == "file"

    def test_skill_manifest_is_a_plain_indexable_file(self):
        assert parse_kind(Path("/.agents/skills/pdf-processing/SKILL.md")) == "file"

    def test_bundled_resource_is_a_plain_file(self):
        assert parse_kind(Path("/.agents/tools/clone-repo/scripts/run.py")) == "file"

    def test_unknown_family_is_a_plain_directory(self):
        assert parse_kind(Path("/.agents/memories/notes")) == "directory"

    def test_agents_lookalike_user_path_not_misclassified(self):
        assert parse_kind(Path("/.agents-archive/tools/x")) == "directory"

    # --- builders ---

    def test_tool_path(self):
        assert tool_path("clone-repo") == "/.agents/tools/clone-repo"

    def test_skill_path(self):
        assert skill_path("pdf-processing") == "/.agents/skills/pdf-processing"

    def test_tool_manifest_path(self):
        assert tool_manifest_path("clone-repo") == "/.agents/tools/clone-repo/TOOL.md"

    def test_skill_manifest_path(self):
        assert skill_manifest_path("pdf-processing") == "/.agents/skills/pdf-processing/SKILL.md"

    def test_builder_kind_roundtrip(self):
        assert parse_kind(tool_path("x")) == "directory"
        assert parse_kind(skill_path("y")) == "directory"
        assert parse_kind(tool_manifest_path("x")) == "file"

    @pytest.mark.parametrize("bad", ["", "a/b", ".", ".."])
    def test_builders_reject_bad_names(self, bad):
        with pytest.raises(ValueError):
            tool_path(bad)


# =========================================================================
# is_meta_path
# =========================================================================


class TestIsMetaPath:
    def test_requires_exact_reserved_prefix(self):
        assert is_meta_path(Path("/.vfs/src/auth.py")) is True
        assert is_meta_path(Path("/.vfs")) is True
        assert is_meta_path(Path("/.vfssrc/auth.py")) is False
        assert is_meta_path(Path("/src/auth.py")) is False


# =========================================================================
# compute_parent_dir
# =========================================================================


class TestParentDir:
    def test_file(self):
        assert compute_parent_dir(Path("/src/auth.py")) == "/src"

    def test_root_child(self):
        assert compute_parent_dir(Path("/src")) == "/"

    def test_root_is_own_parent(self):
        assert compute_parent_dir(Path("/")) == "/"

    def test_meta_scope_path(self):
        assert compute_parent_dir(Path("/.vfs/trash/2026-07-18-10/x.txt")) == "/.vfs/trash/2026-07-18-10"

    def test_returns_vfspath(self):
        result = compute_parent_dir(Path("/src/auth.py"))
        assert isinstance(result, Path)
        assert result == "/src"


# =========================================================================
# extract_extension
# =========================================================================


class TestExtractExtension:
    def test_simple_extension(self):
        assert extract_extension(Path("/src/auth.py")) == "py"

    def test_multi_dot_returns_last(self):
        assert extract_extension(Path("/src/foo.test.py")) == "py"

    def test_lowercased(self):
        assert extract_extension(Path("/src/Foo.PY")) == "py"

    def test_no_extension_returns_none(self):
        assert extract_extension(Path("/Makefile")) is None

    def test_dotfile_returns_none(self):
        assert extract_extension(Path("/.env")) is None

    def test_dotfile_with_extension(self):
        assert extract_extension(Path("/.eslintrc.json")) == "json"

    def test_empty_path(self):
        assert extract_extension("") is None  # ty: ignore[invalid-argument-type]

    def test_root(self):
        assert extract_extension(Path("/")) is None

    def test_directory(self):
        assert extract_extension(Path("/src")) is None

    def test_dotted_directory_name_carries_its_ext(self):
        # POSIX parity: derivation is path-only, kind never gates it.
        assert extract_extension(Path("/a/foo.bar")) == "bar"

    def test_trailing_dot(self):
        assert extract_extension(Path("/src/foo.")) is None

    def test_over_long_extension_rejected(self):
        # Extensions longer than 32 chars return None to keep the index clean.
        long_ext = "x" * 33
        assert extract_extension(Path(f"/src/foo.{long_ext}")) is None

    def test_max_length_extension_accepted(self):
        ext = "x" * 32
        assert extract_extension(Path(f"/src/foo.{ext}")) == ext

    def test_numeric_extension(self):
        assert extract_extension(Path("/archive/old.123")) == "123"

    def test_path_normalized_first(self):
        assert extract_extension("/src//auth.py") == "py"  # ty: ignore[invalid-argument-type]


# =========================================================================
# check_mutable_path relies on its Path arg being canonical
# =========================================================================


class TestCheckMutablePathContract:
    """``check_mutable_path`` takes a Path; non-canonical input cannot reach it.

    The pathological ``/.vfs/..`` cannot exist as a Path (it canonicalizes to
    ``/``), and the gate normalizes before calling, so the write check never sees
    an un-normalized ``..`` that would slip past the root guard.
    """

    def test_gate_rejects_dotdot_into_root(self):
        result = resolve_path("/.vfs/..", mutation=True)
        assert result.path is None
        assert result.error == "Cannot mutate root path"

    def test_gate_rejects_dotdot_into_metadata_root(self):
        # /.vfs/foo/.. canonicalizes to /.vfs
        result = resolve_path("/.vfs/foo/..", mutation=True)
        assert result.path is None
        assert result.error is not None
        assert "metadata root" in result.error

    def test_vfspath_cannot_hold_noncanonical_value(self):
        assert Path("/.vfs/..") == "/"
        assert Path("/.vfs/foo/..") == "/.vfs"

    def test_canonical_vfspath_verdicts(self):
        assert check_mutable_path(Path("/")) == (False, "Cannot mutate root path")
        assert check_mutable_path(Path("/.vfs")) == (
            False,
            "Cannot mutate reserved metadata root '/.vfs'",
        )
        assert check_mutable_path(Path("/src/auth.py")) == (True, "")


# =========================================================================
# resolve_path never raises; Path(non-str) raises ValueError
# =========================================================================


class TestNonStrInput:
    @pytest.mark.parametrize("value", [123, 12.5, b"/a/b", None, ["/a"], {"a": 1}, object()])
    def test_resolve_path_never_raises_on_non_str(self, value):
        result = resolve_path(value)
        assert result.path is None
        assert result.error

    @pytest.mark.parametrize("value", [123, b"/a/b", None, object()])
    def test_vfspath_raises_value_error_not_type_error(self, value):
        with pytest.raises(ValueError):
            Path(value)


# =========================================================================
# validate_path rejects surrogates and bidi/zero-width/format chars
# =========================================================================


class TestDangerousUnicode:
    @pytest.mark.parametrize(
        "code",
        [0x202E, 0x202A, 0x202D, 0x2066, 0x2069, 0x200B, 0x200E, 0x200F, 0x2060, 0xFEFF, 0x2028, 0x2029, 0x00AD],
        ids=lambda c: f"U+{c:04X}",
    )
    def test_format_and_bidi_chars_rejected(self, code):
        ok, _ = validate_path(f"/a{chr(code)}b")
        assert ok is False

    @pytest.mark.parametrize("code", [0xD800, 0xDBFF, 0xDFFF])
    def test_lone_surrogates_rejected(self, code):
        ok, _ = validate_path("/a" + chr(code) + "b")
        assert ok is False

    def test_resolve_path_never_raises_on_surrogate(self):
        result = resolve_path("/a" + chr(0xD800) + "b")
        assert result.path is None
        assert result.error

    def test_vfspath_raises_on_bidi_override(self):
        with pytest.raises(ValueError):
            Path("/a‮b")

    @pytest.mark.parametrize("code", [0x200C, 0x200D])
    def test_zwj_zwnj_are_allowed(self, code):
        # ZWNJ / ZWJ are legitimate in scripts and emoji sequences.
        ok, _ = validate_path(f"/a{chr(code)}b")
        assert ok is True


# =========================================================================
# RelativePath — the relative, contained path gate
# =========================================================================


class TestRelativePath:
    def test_plain_relative_path_is_kept(self):
        rel = RelativePath("scripts/extract.py")
        assert rel == "scripts/extract.py"
        assert isinstance(rel, RelativePath)
        assert isinstance(rel, str)

    def test_canonicalizes_dots_slashes_and_whitespace(self):
        assert RelativePath("scripts//extract.py") == "scripts/extract.py"
        assert RelativePath("scripts/./extract.py") == "scripts/extract.py"
        assert RelativePath(" scripts / extract.py ") == "scripts/extract.py"
        assert RelativePath("scripts/extract.py/") == "scripts/extract.py"

    def test_name_is_the_leaf(self):
        assert RelativePath("references/api/REFERENCE.md").name == "REFERENCE.md"
        assert RelativePath("TOP").name == "TOP"

    def test_absolute_input_is_rejected(self):
        with pytest.raises(ValueError, match="must not be absolute"):
            RelativePath("/scripts/extract.py")

    def test_parent_traversal_is_rejected(self):
        with pytest.raises(ValueError, match=r"must not contain '\.\.'"):
            RelativePath("../escape")
        with pytest.raises(ValueError, match=r"must not contain '\.\.'"):
            RelativePath("scripts/../../escape")

    def test_empty_after_normalization_is_rejected(self):
        # "//" starts with a slash, so it is rejected as absolute, not empty.
        for bad in ("", "   ", ".", "./."):
            with pytest.raises(ValueError, match="must not be empty"):
                RelativePath(bad)

    def test_control_chars_and_overlong_segments_rejected(self):
        with pytest.raises(ValueError, match="control character"):
            RelativePath("scripts/ex\x01tract.py")
        with pytest.raises(ValueError, match="segment too long"):
            RelativePath("a" * 256)

    def test_total_path_over_limit_is_rejected(self):
        # Segments each within the 255 cap, but the whole path exceeds 1024.
        with pytest.raises(ValueError, match="Path too long"):
            RelativePath("/".join(["a" * 250] * 5))

    def test_joining_onto_a_root_stays_contained(self):
        root = Path("/.agents/skills/pdf-processing")
        joined = root.joinpath(RelativePath("scripts/extract.py"))
        assert joined == "/.agents/skills/pdf-processing/scripts/extract.py"
        assert joined.startswith(root + "/")

    def test_resolve_is_non_raising(self):
        ok = resolve_relative_path("scripts/x.py")
        assert isinstance(ok, ResolvedRelativePath)
        assert ok.path == "scripts/x.py"
        assert ok.error is None
        bad = resolve_relative_path("/abs")
        assert bad.path is None
        assert bad.error is not None
        assert "absolute" in bad.error

    def test_resolve_rejects_non_string(self):
        result = resolve_relative_path(123)  # ty: ignore[invalid-argument-type]
        assert result.path is None
        assert result.error is not None
        assert "must be a string" in result.error

    def test_primitives_match_the_gate(self):
        assert normalize_relative_path(" a/./b// ") == "a/b"
        ok, _ = validate_relative_path("a/b")
        assert ok
        bad, reason = validate_relative_path("a/../b")
        assert not bad
        assert ".." in reason

    def test_coerces_at_model_boundary(self):
        class M(BaseModel):
            path: RelativePath

        assert M(path="scripts//x.py").path == "scripts/x.py"
        assert isinstance(M(path="scripts/x.py").path, RelativePath)
        with pytest.raises(ValidationError):
            M(path="/absolute")
