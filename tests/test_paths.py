"""Tests for vfs.paths — the path gate, Path, and the pure helpers it composes.

Self-contained: imports only from ``vfs.paths`` (no backends, models, or fixtures)
so it collects and runs while the rest of the tree is mid-refactor.
"""

from __future__ import annotations

import time

import pytest
from pydantic import BaseModel, ValidationError

from vfs.paths import (
    METADATA_ROOT,
    EdgeParts,
    ResolvedPath,
    Path,
    _canonical_endpoint_path,
    _is_reserved_metadata_directory,
    _split_edge_path,
    _split_nested_endpoint,
    check_mutable_path,
    chunk_path,
    compute_parent_dir,
    compute_parent_file,
    decompose_edge,
    edge_in_path,
    edge_out_path,
    extract_extension,
    is_meta_path,
    normalize_path,
    parse_kind,
    resolve_path,
    split_path,
    validate_path,
    version_path,
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
        nfd = "/café"
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
        assert split_path("/") == ("/", "")

    def test_single_segment(self):
        assert split_path("/foo") == ("/", "foo")

    def test_nested(self):
        assert split_path("/src/auth.py") == ("/src", "auth.py")

    def test_metadata_path_is_literal_split(self):
        # split_path is a pure string operation, not metadata-aware
        assert split_path("/.vfs/src/auth.py/__meta__/chunks/login") == (
            "/.vfs/src/auth.py/__meta__/chunks",
            "login",
        )

    def test_edge_path_is_literal_split(self):
        assert split_path("/.vfs/src/auth.py/__meta__/edges/out/imports/src/utils.py") == (
            "/.vfs/src/auth.py/__meta__/edges/out/imports/src",
            "utils.py",
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
            "/.vfs/src/auth.py/__meta__/chunks/1/login",
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


# =========================================================================
# check_mutable_path
# =========================================================================


class TestCheckMutablePath:
    def test_root_is_not_mutable(self):
        assert check_mutable_path(Path("/")) == (False, "Cannot mutate root path")

    def test_reserved_metadata_root_is_not_mutable(self):
        assert check_mutable_path(Path(METADATA_ROOT)) == (False, "Cannot mutate reserved metadata root '/.vfs'")

    def test_inverse_edge_paths_are_read_only(self):
        valid, err = check_mutable_path(edge_in_path(Path("/src/a.py"), Path("/src/b.py"), "imports"))
        assert valid is False
        assert "inverse edge paths" in err

    def test_reserved_metadata_directories_are_allowed(self):
        assert check_mutable_path(Path("/.vfs/src/auth.py/__meta__/chunks")) == (True, "")

    def test_meta_segment_directory_is_allowed(self):
        assert check_mutable_path(Path("/.vfs/src/auth.py/__meta__")) == (True, "")

    def test_non_metadata_paths_are_mutable(self):
        assert check_mutable_path(Path("/src/auth.py")) == (True, "")

    def test_chunk_and_version_paths_are_mutable(self):
        assert check_mutable_path(Path("/.vfs/src/auth.py/__meta__/chunks/1/login")) == (True, "")
        assert check_mutable_path(Path("/.vfs/src/auth.py/__meta__/versions/3")) == (True, "")

    def test_outbound_edge_paths_are_mutable(self):
        assert check_mutable_path(edge_out_path(Path("/src/a.py"), Path("/src/b.py"), "imports")) == (True, "")

    def test_non_reserved_meta_segment_suffix_is_allowed(self):
        assert check_mutable_path(Path("/.vfs/src/auth.py/custom/__meta__")) == (True, "")

    def test_arbitrary_content_in_reserved_metadata_space_is_rejected(self):
        valid, err = check_mutable_path(Path("/.vfs/src/auth.py/random.txt"))
        assert valid is False
        assert "reserved metadata space" in err


# =========================================================================
# resolve_path  (the gate)
# =========================================================================


class TestResolvePath:
    def test_valid_returns_canonical_vfspath(self):
        result = resolve_path("/src/auth.py")
        assert result == ResolvedPath("/src/auth.py", None)
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
            "/.vfs/src/auth.py/__meta__/chunks/1/login",
            "/.vfs/src/auth.py/__meta__/versions/3",
            "/.vfs/src/auth.py/__meta__/edges/out/imports/src/utils.py",
        ],
    )
    def test_parent_dir_matches_helper(self, path):
        assert Path(path).parent_dir == compute_parent_dir(path)

    def test_parent_file_none_for_plain_paths(self):
        assert Path("/src/auth.py").parent_file is None
        assert Path("/src").parent_file is None

    @pytest.mark.parametrize(
        "path",
        [
            "/.vfs/src/auth.py/__meta__/chunks/1/login",
            "/.vfs/src/auth.py/__meta__/versions/3",
            "/.vfs/src/auth.py/__meta__/edges/out/imports/src/utils.py",
        ],
    )
    def test_parent_file_matches_helper(self, path):
        expected = compute_parent_file(Path(path))
        assert expected is not None
        result = Path(path).parent_file
        assert result == expected
        assert isinstance(result, Path)

    @pytest.mark.parametrize(
        "path",
        [
            "/.vfs/src/auth.py/__meta__/edges/out/imports/src/utils.py",
            "/.vfs/src/auth.py/__meta__/edges/in/imports/src/utils.py",
        ],
    )
    def test_source_target_file_match_decompose(self, path):
        parts = decompose_edge(Path(path))
        assert parts is not None
        source = Path(path).source_file
        target = Path(path).target_file
        assert source == parts.source
        assert target == parts.target
        assert isinstance(source, Path)
        assert isinstance(target, Path)

    def test_source_target_file_none_for_non_edge(self):
        for path in ("/src/auth.py", "/.vfs/src/auth.py/__meta__/versions/3"):
            assert Path(path).source_file is None
            assert Path(path).target_file is None

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
            "/.vfs/src/auth.py/__meta__/chunks/1/login",
            "/.vfs/src/auth.py/__meta__/versions/3",
            "/.vfs/src/auth.py/__meta__/edges/out/imports/src/utils.py",
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
            ("/src", None),  # directory
            ("/.vfs/src/auth.py/__meta__/chunks/1/login", None),  # chunk
            ("/.vfs/src/auth.py/__meta__/versions/3", None),  # version
            ("/.vfs/a.py/__meta__/edges/out/imports/src/utils.py", None),  # edge: .py leaf gated to None
        ],
    )
    def test_ext_is_kind_gated(self, path, ext):
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
            "/.vfs/src/auth.py/__meta__/chunks/1/login",
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
            "/.vfs/src/auth.py/__meta__/chunks/1/0_5",
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
# parse_kind
# =========================================================================


class TestParseKind:
    # --- Metadata markers ---

    def test_chunk(self):
        assert parse_kind("/.vfs/src/auth.py/__meta__/chunks/1/login") == "chunk"

    def test_version(self):
        assert parse_kind("/.vfs/src/auth.py/__meta__/versions/3") == "version"

    def test_edge(self):
        assert parse_kind("/.vfs/src/auth.py/__meta__/edges/out/imports/src/utils.py") == "edge"

    # --- Files with extensions ---

    @pytest.mark.parametrize("path", ["/src/auth.py", "/docs/readme.md", "/data/report.pdf"])
    def test_file_with_extension(self, path):
        assert parse_kind(path) == "file"

    def test_multiple_extensions(self):
        assert parse_kind("/archive.tar.gz") == "file"

    def test_trailing_dot(self):
        # file. has a dot at position > 0
        assert parse_kind("/file.") == "file"

    # --- Dotfiles ---

    @pytest.mark.parametrize("name", [".bashrc", ".gitconfig", ".hidden", ".vimrc"])
    def test_unlisted_dotfiles_are_files(self, name):
        assert parse_kind(f"/home/{name}") == "file"

    def test_listed_dotfile(self):
        assert parse_kind("/.gitignore") == "file"

    def test_dotfile_with_extension(self):
        assert parse_kind("/.env.local") == "file"

    # --- Dot-prefixed user paths remain ordinary files ---

    @pytest.mark.parametrize("name", [".chunks", ".versions", ".connections"])
    def test_dot_prefixed_metadata_like_names_are_files(self, name):
        assert parse_kind(f"/foo/{name}") == "file"

    # --- Extensionless files (case-insensitive) ---

    @pytest.mark.parametrize("name", ["Makefile", "makefile", "MAKEFILE"])
    def test_makefile_case_insensitive(self, name):
        assert parse_kind(f"/{name}") == "file"

    @pytest.mark.parametrize("name", ["LICENSE", "license", "License"])
    def test_license_case_insensitive(self, name):
        assert parse_kind(f"/{name}") == "file"

    def test_dockerfile(self):
        assert parse_kind("/Dockerfile") == "file"

    # --- Directories ---

    @pytest.mark.parametrize("path", ["/src", "/documents", "/", "/people/teams"])
    def test_directories(self, path):
        assert parse_kind(path) == "directory"

    def test_nested_chunk_descendants_stay_classified_as_chunks(self):
        assert parse_kind("/.vfs/src/auth.py/__meta__/chunks/login/body.txt") == "chunk"

    def test_nested_version_descendants_stay_classified_as_versions(self):
        assert parse_kind("/.vfs/src/auth.py/__meta__/versions/3/body.txt") == "version"

    def test_incomplete_edge_without_target_is_a_directory(self):
        # Edge type but no target is not a complete projected edge — it is the
        # type-scoped directory, mirroring the incomplete-chunk rule.
        assert parse_kind("/.vfs/foo/__meta__/edges/out/imports") == "directory"

    # --- Marker boundary (no false positives) ---

    def test_similar_name_not_misclassified(self):
        # Similar user paths should not be mistaken for reserved metadata roots.
        assert parse_kind("/my-connections/file.sql") == "file"

    def test_metadata_root_is_classified_as_directory(self):
        assert parse_kind(METADATA_ROOT) == "directory"

    def test_metadata_tree_paths_are_classified_as_directories(self):
        assert parse_kind("/.vfs/src/auth.py") == "directory"


# =========================================================================
# meta_root + endpoint_root + compute_parent_file
# =========================================================================


class TestNamespaceRoots:
    def test_compute_parent_file_for_chunk(self):
        assert compute_parent_file(Path("/.vfs/src/auth.py/__meta__/chunks/1/login")) == "/src/auth.py"

    def test_compute_parent_file_for_version(self):
        assert compute_parent_file(Path("/.vfs/src/auth.py/__meta__/versions/3")) == "/src/auth.py"

    def test_compute_parent_file_for_edge(self):
        assert (
            compute_parent_file(Path("/.vfs/src/auth.py/__meta__/edges/out/imports/src/utils.py")) == "/src/auth.py"
        )

    def test_compute_parent_file_none_for_plain_file(self):
        assert compute_parent_file(Path("/src/auth.py")) is None

    def test_is_meta_path_requires_exact_reserved_prefix(self):
        assert is_meta_path("/.vfs/src/auth.py") is True
        assert is_meta_path("/.vfssrc/auth.py") is False


# =========================================================================
# compute_parent_dir
# =========================================================================


class TestParentDir:
    def test_file(self):
        assert compute_parent_dir("/src/auth.py") == "/src"

    def test_root_child(self):
        assert compute_parent_dir("/src") == "/"

    def test_root_is_own_parent(self):
        assert compute_parent_dir("/") == "/"

    def test_chunk(self):
        assert compute_parent_dir("/.vfs/src/auth.py/__meta__/chunks/login") == "/.vfs/src/auth.py/__meta__/chunks"

    def test_version(self):
        assert compute_parent_dir("/.vfs/src/auth.py/__meta__/versions/3") == "/.vfs/src/auth.py/__meta__/versions"

    def test_edge(self):
        assert (
            compute_parent_dir("/.vfs/src/auth.py/__meta__/edges/out/imports/src/utils.py")
            == "/.vfs/src/auth.py/__meta__/edges/out/imports/src"
        )

    def test_bare_metadata_dir(self):
        assert compute_parent_dir("/.vfs/src/auth.py/__meta__/chunks") == "/.vfs/src/auth.py/__meta__"


# =========================================================================
# chunk_path
# =========================================================================


class TestChunkPath:
    def test_basic(self):
        assert chunk_path(Path("/src/auth.py"), "login", 1) == "/.vfs/src/auth.py/__meta__/chunks/1/login"

    def test_normalizes_file_path(self):
        # Path canonicalizes the base at construction; the builder no longer does.
        assert chunk_path(Path("src/auth.py"), "login", 2) == "/.vfs/src/auth.py/__meta__/chunks/2/login"

    def test_roundtrip_parse_kind(self):
        assert parse_kind(chunk_path(Path("/f.py"), "x", 1)) == "chunk"

    def test_empty_name_rejected(self):
        with pytest.raises(ValueError, match="chunk_name"):
            chunk_path(Path("/f.py"), "", 1)

    def test_slash_in_name_rejected(self):
        with pytest.raises(ValueError, match="chunk_name"):
            chunk_path(Path("/f.py"), "a/b", 1)

    def test_metadata_base_rejected(self):
        with pytest.raises(ValueError, match="metadata"):
            chunk_path(Path("/.vfs/f.py/__meta__/chunks/1/login"), "x", 1)

    def test_reserved_ending_rejected(self):
        with pytest.raises(ValueError, match="metadata path"):
            chunk_path(Path("/.vfs/foo/__meta__/chunks"), "x", 1)

    def test_root_base_rejected(self):
        with pytest.raises(ValueError, match="root or reserved metadata root"):
            chunk_path(Path("/"), "x", 1)


# =========================================================================
# version_path
# =========================================================================


class TestVersionPath:
    def test_basic(self):
        assert version_path(Path("/src/auth.py"), 3) == "/.vfs/src/auth.py/__meta__/versions/3"

    def test_roundtrip_parse_kind(self):
        assert parse_kind(version_path(Path("/f.py"), 1)) == "version"

    def test_negative_rejected(self):
        with pytest.raises(ValueError, match="version_number"):
            version_path(Path("/f.py"), -1)

    def test_zero_rejected(self):
        with pytest.raises(ValueError, match="version_number"):
            version_path(Path("/f.py"), 0)

    def test_metadata_base_rejected(self):
        with pytest.raises(ValueError, match="metadata"):
            version_path(Path("/.vfs/f.py/__meta__/versions/1"), 2)


# =========================================================================
# edge_out_path + decompose_edge (roundtrip)
# =========================================================================


class TestEdgePath:
    def test_basic(self):
        assert (
            edge_out_path(Path("/src/auth.py"), Path("/src/utils.py"), "imports")
            == "/.vfs/src/auth.py/__meta__/edges/out/imports/src/utils.py"
        )

    def test_roundtrip(self):
        cases = [
            ("/src/auth.py", "/src/utils.py", "imports"),
            ("/jira/PROJ-1", "/src/auth.py", "references"),
            ("/a.py", "/deep/nested/path.py", "calls"),
        ]
        for s, t, c in cases:
            path = edge_out_path(Path(s), Path(t), c)
            parts = decompose_edge(path)
            assert parts == EdgeParts(source=s, target=t, edge_type=c, direction="out")

    def test_normalizes_target(self):
        p = edge_out_path(Path("/a.py"), Path("src//utils.py"), "imports")
        assert p == "/.vfs/a.py/__meta__/edges/out/imports/src/utils.py"

    def test_empty_type_rejected(self):
        with pytest.raises(ValueError, match="edge_type"):
            edge_out_path(Path("/a.py"), Path("/b.py"), "")

    def test_slash_in_type_rejected(self):
        with pytest.raises(ValueError, match="edge_type"):
            edge_out_path(Path("/a.py"), Path("/b.py"), "calls/async")

    def test_root_target_rejected(self):
        with pytest.raises(ValueError, match="target"):
            edge_out_path(Path("/a.py"), Path("/"), "imports")

    def test_source_meta_path_rejected(self):
        with pytest.raises(ValueError, match="metadata path"):
            edge_out_path(Path("/.vfs/a.py/__meta__/edges/out/imports/b.py"), Path("/c.py"), "calls")

    def test_target_meta_path_rejected(self):
        with pytest.raises(ValueError, match="metadata path"):
            edge_out_path(Path("/a.py"), Path("/.vfs/b.py/__meta__/edges/out"), "calls")

    def test_bare_meta_endpoint_rejected(self):
        # An edge endpoint may not live in reserved /.vfs space, even without a __meta__ frame.
        with pytest.raises(ValueError, match="metadata path"):
            edge_out_path(Path("/.vfs/foo"), Path("/b.py"), "imports")


class TestDecomposeEdge:
    def test_basic(self):
        result = decompose_edge("/.vfs/src/auth.py/__meta__/edges/out/imports/src/utils.py")
        assert result == EdgeParts(
            source="/src/auth.py",
            target="/src/utils.py",
            edge_type="imports",
            direction="out",
        )

    def test_not_a_connection(self):
        assert decompose_edge("/src/auth.py") is None

    def test_type_only_no_target(self):
        assert decompose_edge("/.vfs/foo/__meta__/edges/out/imports") is None

    def test_deep_target(self):
        result = decompose_edge("/.vfs/a.py/__meta__/edges/out/calls/src/deep/nested/path.py")
        assert result is not None
        assert result.source == "/a.py"
        assert result.target == "/src/deep/nested/path.py"
        assert result.edge_type == "calls"
        assert result.direction == "out"

    def test_named_access(self):
        result = decompose_edge("/.vfs/a.py/__meta__/edges/out/imports/b.py")
        assert result is not None
        assert result.source == "/a.py"
        assert result.target == "/b.py"
        assert result.edge_type == "imports"
        # Positional matches named
        assert result[0] == result.source
        assert result[1] == result.target
        assert result[2] == result.edge_type
        assert result[3] == result.direction


# =========================================================================
# extract_extension
# =========================================================================


class TestExtractExtension:
    def test_simple_extension(self):
        assert extract_extension("/src/auth.py") == "py"

    def test_multi_dot_returns_last(self):
        assert extract_extension("/src/foo.test.py") == "py"

    def test_lowercased(self):
        assert extract_extension("/src/Foo.PY") == "py"

    def test_no_extension_returns_none(self):
        assert extract_extension("/Makefile") is None

    def test_dotfile_returns_none(self):
        assert extract_extension("/.env") is None

    def test_dotfile_with_extension(self):
        assert extract_extension("/.eslintrc.json") == "json"

    def test_empty_path(self):
        assert extract_extension("") is None

    def test_root(self):
        assert extract_extension("/") is None

    def test_directory(self):
        assert extract_extension("/src") is None

    def test_trailing_dot(self):
        assert extract_extension("/src/foo.") is None

    def test_over_long_extension_rejected(self):
        # Extensions longer than 32 chars return None to keep the index clean.
        long_ext = "x" * 33
        assert extract_extension(f"/src/foo.{long_ext}") is None

    def test_max_length_extension_accepted(self):
        ext = "x" * 32
        assert extract_extension(f"/src/foo.{ext}") == ext

    def test_numeric_extension(self):
        assert extract_extension("/archive/old.123") == "123"

    def test_path_normalized_first(self):
        assert extract_extension("/src//auth.py") == "py"


# =========================================================================
# Internal helper coverage
# =========================================================================


class TestPathInternals:
    def test_edge_path_split_requires_embedded_path(self):
        assert _split_edge_path("/.vfs/a.py/__meta__/edges/out/imports") is None

    def test_edge_path_split_requires_edge_type(self):
        assert _split_edge_path("/.vfs/a.py/__meta__/edges/out//b.py") is None

    def test_canonical_endpoint_leaves_user_paths_unchanged(self):
        assert _canonical_endpoint_path("/src/auth.py") == "/src/auth.py"

    def test_canonical_endpoint_rejects_reserved_metadata_root(self):
        with pytest.raises(ValueError, match="not a canonical endpoint"):
            _canonical_endpoint_path(METADATA_ROOT)

    def test_canonical_endpoint_strips_metadata_root_prefix(self):
        assert _canonical_endpoint_path("/.vfs/src/auth.py") == "/src/auth.py"

    def test_canonical_endpoint_preserves_nested_chunk_root(self):
        assert _canonical_endpoint_path("/.vfs/src/auth.py/__meta__/chunks/1/login/body.txt") == (
            "/.vfs/src/auth.py/__meta__/chunks/1/login"
        )

    def test_split_nested_endpoint_returns_endpoint_when_path_stops_at_version(self):
        path = "/.vfs/src/auth.py/__meta__/versions/3"
        assert _split_nested_endpoint(path) == path

    def test_split_nested_endpoint_collapses_descendant_to_nested_root(self):
        assert _split_nested_endpoint("/.vfs/src/auth.py/__meta__/versions/3/body.txt") == (
            "/.vfs/src/auth.py/__meta__/versions/3"
        )

    def test_reserved_metadata_directory_check_is_false_outside_metadata_tree(self):
        assert _is_reserved_metadata_directory("/src/auth.py/__meta__/chunks") is False


# =========================================================================
# Metadata classification is anchored at /.vfs
# =========================================================================


class TestMetadataAnchoring:
    """A path NOT under /.vfs is never metadata, even if it embeds the markers."""

    def test_ordinary_edge_marker_path_is_not_an_edge(self):
        assert parse_kind("/foo/__meta__/edges/out/imports/bar.py") == "file"

    def test_ordinary_chunk_marker_path_is_not_a_chunk(self):
        # Leaf has no extension and is not an extensionless special -> directory.
        assert parse_kind("/foo/__meta__/chunks/1/login") == "directory"

    def test_ordinary_chunk_marker_path_with_extension_is_a_file(self):
        assert parse_kind("/foo/__meta__/chunks/1/login.txt") == "file"

    def test_decompose_edge_returns_none_for_non_meta_path(self):
        assert decompose_edge("/foo/__meta__/edges/out/imports/bar") is None

    def test_compute_parent_file_none_for_non_meta_marker_path(self):
        assert compute_parent_file(Path("/foo/__meta__/chunks/1/login")) is None

    def test_split_edge_path_requires_metadata_root(self):
        assert _split_edge_path("/foo/__meta__/edges/out/imports/bar") is None

    def test_split_nested_endpoint_requires_metadata_root(self):
        assert _split_nested_endpoint("/foo/__meta__/chunks/1/login") is None

    def test_metadata_under_vfs_still_classifies(self):
        # Sanity: real metadata still works after anchoring.
        assert parse_kind("/.vfs/foo/__meta__/edges/out/imports/bar") == "edge"
        assert parse_kind("/.vfs/foo/__meta__/chunks/1/login") == "chunk"


# =========================================================================
# Nested __meta__ frames are rejected at the gate
# =========================================================================


class TestNestedMetaRejected:
    """At most one ``__meta__`` segment per path; cross-family nesting is illegal."""

    @pytest.mark.parametrize(
        "path",
        [
            # chunk cannot contain versions
            "/.vfs/f.py/__meta__/chunks/1/x/__meta__/versions/2",
            # versions cannot contain edges
            "/.vfs/f.py/__meta__/versions/2/__meta__/edges/out/imports/g.py",
            # edges cannot contain chunks
            "/.vfs/f.py/__meta__/edges/out/imports/g.py/__meta__/chunks/1/x",
        ],
    )
    def test_validate_path_rejects_nested_meta(self, path):
        ok, reason = validate_path(path)
        assert ok is False
        assert "__meta__" in reason or "nested" in reason.lower()

    def test_resolve_path_rejects_nested_meta(self):
        result = resolve_path("/.vfs/f.py/__meta__/chunks/1/x/__meta__/versions/2")
        assert result.path is None
        assert result.error

    def test_single_meta_frame_is_allowed(self):
        ok, _ = validate_path("/.vfs/f.py/__meta__/chunks/1/x")
        assert ok is True

    def test_inverse_edge_mutability_bypass_is_rejected_at_gate(self):
        # Crafted out-after-in path that previously parsed as a writable out-edge.
        bypass = "/.vfs/A/__meta__/edges/in/t/B/__meta__/edges/out/t2/C"
        assert resolve_path(bypass, mutation=True).path is None
        assert resolve_path(bypass).path is None

    def test_single_meta_in_ordinary_path_is_still_allowed(self):
        # One literal __meta__ segment outside /.vfs is a normal directory name.
        ok, _ = validate_path("/foo/__meta__/bar")
        assert ok is True


# =========================================================================
# The metadata grammar is enforced at the gate
# =========================================================================


class TestMetaGrammarRejected:
    """Malformed metadata paths are not valid Paths — the gate rejects them."""

    @pytest.mark.parametrize(
        "path",
        [
            # descendants below a complete endpoint (endpoints are terminal)
            "/.vfs/f.py/__meta__/chunks/1/name/extra",
            "/.vfs/f.py/__meta__/chunks/1/name/a/b/c",
            "/.vfs/f.py/__meta__/versions/3/extra",
            # versions must be canonical positive integers
            "/.vfs/f.py/__meta__/versions/abc",
            "/.vfs/f.py/__meta__/versions/0",
            "/.vfs/f.py/__meta__/versions/-1",
            "/.vfs/f.py/__meta__/versions/01",
            "/.vfs/f.py/__meta__/chunks/notanumber/x",
            "/.vfs/f.py/__meta__/chunks/0/x",
            # malformed edges / unknown families
            "/.vfs/f.py/__meta__/edges/sideways/imports/t",
            "/.vfs/f.py/__meta__/garbage",
            "/.vfs/f.py/__meta__/garbage/x",
            # owner-less meta frames (nothing between /.vfs and __meta__)
            "/.vfs/__meta__",
            "/.vfs/__meta__/chunks/1/x",
            "/.vfs/__meta__/versions/3",
            "/.vfs/__meta__/edges/out/t/x",
        ],
    )
    def test_malformed_meta_path_is_not_a_vfspath(self, path):
        with pytest.raises(ValueError):
            Path(path)
        assert resolve_path(path).path is None

    def test_empty_owner_edge_does_not_raise_at_mutation_gate(self):
        # Regression: this used to reach decompose_edge and raise instead of rejecting.
        result = resolve_path("/.vfs/__meta__/edges/out/t/x", mutation=True)
        assert result.path is None
        assert result.error


class TestMetaGrammarAccepted:
    """Well-formed skeleton directories and endpoints construct and classify."""

    @pytest.mark.parametrize(
        "path,kind",
        [
            ("/.vfs", "directory"),
            ("/.vfs/f.py", "directory"),
            ("/.vfs/f.py/__meta__", "directory"),
            ("/.vfs/f.py/__meta__/chunks", "directory"),
            ("/.vfs/f.py/__meta__/chunks/1", "directory"),  # version-scoped dir
            ("/.vfs/f.py/__meta__/chunks/1/login", "chunk"),
            ("/.vfs/f.py/__meta__/versions", "directory"),
            ("/.vfs/f.py/__meta__/versions/3", "version"),
            ("/.vfs/f.py/__meta__/edges", "directory"),
            ("/.vfs/f.py/__meta__/edges/out", "directory"),
            ("/.vfs/f.py/__meta__/edges/out/imports", "directory"),
            ("/.vfs/f.py/__meta__/edges/out/imports/src/utils.py", "edge"),
            ("/.vfs/f.py/__meta__/edges/in/imports/src/a.py", "edge"),
        ],
    )
    def test_wellformed_meta_path_constructs_and_classifies(self, path, kind):
        vp = Path(path)
        assert vp.kind == kind


# =========================================================================
# Builders reject dangerous segments and bad versions
# =========================================================================


class TestBuilderSegmentValidation:
    @pytest.mark.parametrize("name", ["..", ".", "a/b"])
    def test_chunk_name_rejects_traversal_and_slash(self, name):
        with pytest.raises(ValueError, match="chunk_name"):
            chunk_path(Path("/a.py"), name, 1)

    @pytest.mark.parametrize("name", ["a\x00b", "a\nb", "a\x7fb"])
    def test_chunk_name_rejects_null_and_control(self, name):
        with pytest.raises(ValueError, match="chunk_name"):
            chunk_path(Path("/a.py"), name, 1)

    @pytest.mark.parametrize("edge_type", ["..", ".", "a\x00b", "a\nb"])
    def test_edge_type_rejects_traversal_null_and_control(self, edge_type):
        with pytest.raises(ValueError, match="edge_type"):
            edge_out_path(Path("/a.py"), Path("/b.py"), edge_type)

    def test_file_base_rejects_embedded_meta_segment(self):
        with pytest.raises(ValueError, match="metadata"):
            chunk_path(Path("/a/__meta__/edges/out/imports/x"), "login", 1)

    def test_edge_endpoint_rejects_embedded_meta_segment(self):
        with pytest.raises(ValueError, match="metadata"):
            edge_out_path(Path("/x/__meta__/edges/out/imports/y"), Path("/b.py"), "rel")

    @pytest.mark.parametrize("version", [0, -1, -5])
    def test_chunk_path_rejects_non_positive_version(self, version):
        with pytest.raises(ValueError, match="version"):
            chunk_path(Path("/a.py"), "x", version)

    @pytest.mark.parametrize("version", [2.9, 2.0, True])
    def test_chunk_version_must_be_int(self, version):
        with pytest.raises(ValueError, match="int"):
            chunk_path(Path("/a.py"), "x", version)

    @pytest.mark.parametrize("version", [2.9, 2.0, True])
    def test_version_number_must_be_int(self, version):
        with pytest.raises(ValueError, match="int"):
            version_path(Path("/a.py"), version)

    def test_valid_builders_still_work(self):
        # Guard against over-rejection.
        assert chunk_path(Path("/a.py"), "login", 1) == "/.vfs/a.py/__meta__/chunks/1/login"
        edge = edge_out_path(Path("/a.py"), Path("/b.py"), "imports")
        assert edge == "/.vfs/a.py/__meta__/edges/out/imports/b.py"


# =========================================================================
# Builders take Path endpoints and return a branded Path
# =========================================================================


class TestBuilderPath:
    def test_chunk_path_returns_vfspath(self):
        result = chunk_path(Path("/a.py"), "login", 1)
        assert isinstance(result, Path)
        assert result == "/.vfs/a.py/__meta__/chunks/1/login"

    def test_version_path_returns_vfspath(self):
        result = version_path(Path("/a.py"), 3)
        assert isinstance(result, Path)
        assert result == "/.vfs/a.py/__meta__/versions/3"

    def test_edge_out_path_returns_vfspath(self):
        result = edge_out_path(Path("/a.py"), Path("/b.py"), "imports")
        assert isinstance(result, Path)
        assert result == "/.vfs/a.py/__meta__/edges/out/imports/b.py"

    def test_edge_in_path_returns_vfspath(self):
        result = edge_in_path(Path("/a.py"), Path("/b.py"), "imports")
        assert isinstance(result, Path)

    def test_branded_output_round_trips(self):
        path = edge_out_path(Path("/src/a.py"), Path("/src/b.py"), "imports")
        assert decompose_edge(path) == EdgeParts("/src/a.py", "/src/b.py", "imports", "out")

    def test_branded_chunk_output_parses_back_to_chunk(self):
        assert parse_kind(chunk_path(Path("/a.py"), "login", 1)) == "chunk"


class TestBuilderRejectsGateRejectedSegments:
    """A name segment the gate would reject must be rejected at build time."""

    @pytest.mark.parametrize("name", ["bad‮", "a﻿b", "a" + chr(0xD800) + "b"])
    def test_chunk_name_rejects_format_and_surrogate(self, name):
        with pytest.raises(ValueError, match="chunk_name"):
            chunk_path(Path("/f.py"), name, 1)

    @pytest.mark.parametrize("edge_type", ["bad‮", "a﻿b", "a" + chr(0xD800) + "b"])
    def test_edge_type_rejects_format_and_surrogate(self, edge_type):
        with pytest.raises(ValueError, match="edge_type"):
            edge_out_path(Path("/a.py"), Path("/b.py"), edge_type)


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
# Incomplete chunk endpoints are directories, not mutable chunks
# =========================================================================


class TestIncompleteEndpoints:
    def test_chunk_version_dir_without_name_is_a_directory(self):
        assert parse_kind("/.vfs/f.py/__meta__/chunks/1") == "directory"

    def test_complete_chunk_is_a_chunk(self):
        assert parse_kind("/.vfs/f.py/__meta__/chunks/1/login") == "chunk"

    def test_complete_version_is_a_version(self):
        assert parse_kind("/.vfs/f.py/__meta__/versions/3") == "version"

    def test_incomplete_chunk_dir_is_not_a_mutable_chunk(self):
        ok, _ = check_mutable_path(Path("/.vfs/f.py/__meta__/chunks/1"))
        assert ok is False


# =========================================================================
# Entry-attribute derivations take a Path and return a branded path
# =========================================================================


class TestEntryDerivationPath:
    def test_compute_parent_dir_returns_vfspath(self):
        result = compute_parent_dir(Path("/src/auth.py"))
        assert isinstance(result, Path)
        assert result == "/src"

    def test_compute_parent_file_returns_vfspath_for_chunk(self):
        result = compute_parent_file(Path("/.vfs/src/auth.py/__meta__/chunks/1/login"))
        assert isinstance(result, Path)
        assert result == "/src/auth.py"

    def test_compute_parent_file_none_for_plain_file(self):
        assert compute_parent_file(Path("/src/auth.py")) is None

    def test_parse_kind_on_vfspath(self):
        assert parse_kind(Path("/.vfs/src/auth.py/__meta__/chunks/1/login")) == "chunk"
        assert parse_kind(Path("/src/auth.py")) == "file"

    def test_vfspath_property_delegates_stay_branded(self):
        p = Path("/.vfs/src/auth.py/__meta__/chunks/1/login")
        assert isinstance(p.parent_dir, Path)
        assert isinstance(p.parent_file, Path)

    def test_extract_extension_accepts_vfspath(self):
        assert extract_extension(Path("/src/auth.py")) == "py"
        assert extract_extension(Path("/Makefile")) is None
