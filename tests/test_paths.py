"""Tests for vfs.paths — path utilities for the ``/.vfs/.../__meta__`` namespace."""

from __future__ import annotations

import pytest

from vfs.paths import (
    MARKER_KINDS,
    METADATA_KIND_MAP,
    METADATA_MARKERS,
    METADATA_ROOT,
    EdgeParts,
    _canonical_endpoint_path,
    _is_reserved_metadata_directory,
    _split_edge_path,
    _split_nested_endpoint,
    _strip_user_prefix,
    api_path,
    base_path,
    chunk_path,
    decompose_edge,
    edge_in_path,
    edge_out_path,
    endpoint_root,
    extract_extension,
    is_meta_root_path,
    meta_root,
    normalize_path,
    owning_file_path,
    parent_path,
    parse_kind,
    scope_path,
    split_path,
    unscope_path,
    validate_mutation_path,
    validate_path,
    validate_user_id,
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

    def test_dot_dot_at_root_clamps(self):
        assert normalize_path("/../../../etc/passwd") == "/etc/passwd"

    def test_metadata_traversal(self):
        assert normalize_path("/.vfs/../../../etc/passwd") == "/etc/passwd"

    def test_nfc_normalization(self):
        # NFD é (e + combining acute) should collapse to NFC é
        nfd = "/caf\u0065\u0301"
        nfc = "/caf\u00e9"
        assert normalize_path(nfd) == normalize_path(nfc)

    def test_whitespace_stripped(self):
        assert normalize_path("  /foo  ") == "/foo"

    def test_only_slashes(self):
        assert normalize_path("///") == "/"

    def test_double_leading_slash_collapses_to_single_rooted_path(self):
        assert normalize_path("//src/auth.py") == "/src/auth.py"


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
            "/.vfs/src/auth.py/__meta__/chunks/login",
            "/.vfs/jira/__meta__/apis/ticket",
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


# =========================================================================
# parse_kind
# =========================================================================


class TestParseKind:
    # --- Metadata markers ---

    def test_chunk(self):
        assert parse_kind("/.vfs/src/auth.py/__meta__/chunks/login") == "chunk"

    def test_version(self):
        assert parse_kind("/.vfs/src/auth.py/__meta__/versions/3") == "version"

    def test_edge(self):
        assert parse_kind("/.vfs/src/auth.py/__meta__/edges/out/imports/src/utils.py") == "edge"

    def test_api(self):
        assert parse_kind("/.vfs/jira/__meta__/apis/ticket") == "api"

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

    @pytest.mark.parametrize("name", [".chunks", ".versions", ".connections", ".apis"])
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

    # --- Marker boundary (no false positives) ---

    def test_similar_name_not_misclassified(self):
        # Similar user paths should not be mistaken for reserved metadata roots.
        assert parse_kind("/my-connections/file.sql") == "file"


# =========================================================================
# base_path
# =========================================================================


class TestBasePath:
    def test_file_returns_self(self):
        assert base_path("/src/auth.py") == "/src/auth.py"

    def test_chunk(self):
        assert base_path("/.vfs/src/auth.py/__meta__/chunks/login") == "/src/auth.py"

    def test_version(self):
        assert base_path("/.vfs/src/auth.py/__meta__/versions/3") == "/src/auth.py"

    def test_connection_deep_target(self):
        assert base_path("/.vfs/src/auth.py/__meta__/edges/out/imports/src/deep/path.py") == "/src/auth.py"

    def test_api(self):
        assert base_path("/.vfs/jira/__meta__/apis/ticket") == "/jira"

    def test_root(self):
        assert base_path("/") == "/"

    def test_metadata_root_maps_back_to_root(self):
        assert base_path(METADATA_ROOT) == "/"

    def test_bare_metadata_dir(self):
        assert base_path("/.vfs/src/auth.py/__meta__/chunks") == "/src/auth.py"
        assert base_path("/.vfs/src/auth.py/__meta__/versions") == "/src/auth.py"
        assert base_path("/.vfs/src/auth.py/__meta__/edges/out") == "/src/auth.py"
        assert base_path("/.vfs/jira/__meta__/apis") == "/jira"

    def test_first_marker_wins(self):
        assert base_path("/.vfs/.vfs/foo/__meta__/chunks/__meta__/versions/1") == "/.vfs/foo"

    def test_hidden_endpoint_without_meta_segment_maps_back_to_user_path(self):
        assert base_path("/.vfs/src/auth.py") == "/src/auth.py"


# =========================================================================
# meta_root + endpoint_root + owning_file_path
# =========================================================================


class TestNamespaceRoots:
    def test_meta_root_prefixes_user_paths(self):
        assert meta_root("/src/auth.py") == "/.vfs/src/auth.py"

    def test_meta_root_preserves_metadata_endpoints(self):
        path = "/.vfs/src/auth.py/__meta__/chunks/login"
        assert meta_root(path) == path

    def test_meta_root_rejects_reserved_root(self):
        with pytest.raises(ValueError, match="Reserved path"):
            meta_root(METADATA_ROOT)

    def test_meta_root_rejects_projected_edge_paths(self):
        with pytest.raises(ValueError, match="Projected edge paths"):
            meta_root("/.vfs/src/auth.py/__meta__/edges/out/imports/src/utils.py")

    def test_meta_root_rejects_reserved_metadata_directories(self):
        with pytest.raises(ValueError, match="Reserved metadata directory"):
            meta_root("/.vfs/src/auth.py/__meta__/chunks")

    def test_endpoint_root_returns_owner_for_projected_edges(self):
        assert endpoint_root("/.vfs/src/auth.py/__meta__/edges/out/imports/src/utils.py") == "/.vfs/src/auth.py"

    def test_endpoint_root_collapses_nested_chunk_children(self):
        assert endpoint_root("/.vfs/src/auth.py/__meta__/chunks/login/body.txt") == (
            "/.vfs/src/auth.py/__meta__/chunks/login"
        )

    def test_endpoint_root_leaves_non_nested_metadata_paths_alone(self):
        assert endpoint_root("/.vfs/src/auth.py") == "/.vfs/src/auth.py"

    def test_owning_file_path_aliases_base_path(self):
        assert owning_file_path("/.vfs/src/auth.py/__meta__/chunks/login") == "/src/auth.py"

    def test_is_meta_root_path_requires_exact_reserved_prefix(self):
        assert is_meta_root_path("/.vfs/src/auth.py") is True
        assert is_meta_root_path("/.vfssrc/auth.py") is False


# =========================================================================
# parent_path
# =========================================================================


class TestParentPath:
    def test_file(self):
        assert parent_path("/src/auth.py") == "/src"

    def test_root_child(self):
        assert parent_path("/src") == "/"

    def test_root_is_own_parent(self):
        assert parent_path("/") == "/"

    def test_chunk(self):
        assert parent_path("/.vfs/src/auth.py/__meta__/chunks/login") == "/.vfs/src/auth.py/__meta__/chunks"

    def test_version(self):
        assert parent_path("/.vfs/src/auth.py/__meta__/versions/3") == "/.vfs/src/auth.py/__meta__/versions"

    def test_edge(self):
        assert (
            parent_path("/.vfs/src/auth.py/__meta__/edges/out/imports/src/utils.py")
            == "/.vfs/src/auth.py/__meta__/edges/out/imports/src"
        )

    def test_api(self):
        assert parent_path("/.vfs/jira/__meta__/apis/ticket") == "/.vfs/jira/__meta__/apis"

    def test_bare_metadata_dir(self):
        assert parent_path("/.vfs/src/auth.py/__meta__/chunks") == "/.vfs/src/auth.py/__meta__"


# =========================================================================
# chunk_path
# =========================================================================


class TestChunkPath:
    def test_basic(self):
        assert chunk_path("/src/auth.py", "login") == "/.vfs/src/auth.py/__meta__/chunks/login"

    def test_normalizes_file_path(self):
        assert chunk_path("src/auth.py", "login") == "/.vfs/src/auth.py/__meta__/chunks/login"

    def test_roundtrip_parse_kind(self):
        assert parse_kind(chunk_path("/f.py", "x")) == "chunk"

    def test_empty_name_rejected(self):
        with pytest.raises(ValueError, match="chunk_name"):
            chunk_path("/f.py", "")

    def test_slash_in_name_rejected(self):
        with pytest.raises(ValueError, match="chunk_name"):
            chunk_path("/f.py", "a/b")

    def test_metadata_base_rejected(self):
        with pytest.raises(ValueError, match="metadata"):
            chunk_path("/.vfs/f.py/__meta__/chunks/bar", "x")

    def test_reserved_ending_rejected(self):
        with pytest.raises(ValueError, match="metadata path"):
            chunk_path("/.vfs/foo/__meta__/chunks", "x")

    def test_root_base_rejected(self):
        with pytest.raises(ValueError, match="root or reserved metadata root"):
            chunk_path("/", "x")


# =========================================================================
# version_path
# =========================================================================


class TestVersionPath:
    def test_basic(self):
        assert version_path("/src/auth.py", 3) == "/.vfs/src/auth.py/__meta__/versions/3"

    def test_roundtrip_parse_kind(self):
        assert parse_kind(version_path("/f.py", 1)) == "version"

    def test_negative_rejected(self):
        with pytest.raises(ValueError, match="version_number"):
            version_path("/f.py", -1)

    def test_zero_rejected(self):
        with pytest.raises(ValueError, match="version_number"):
            version_path("/f.py", 0)

    def test_metadata_base_rejected(self):
        with pytest.raises(ValueError, match="metadata"):
            version_path("/.vfs/f.py/__meta__/versions/1", 2)


# =========================================================================
# edge_out_path + decompose_edge (roundtrip)
# =========================================================================


class TestEdgePath:
    def test_basic(self):
        assert (
            edge_out_path("/src/auth.py", "/src/utils.py", "imports")
            == "/.vfs/src/auth.py/__meta__/edges/out/imports/src/utils.py"
        )

    def test_roundtrip(self):
        cases = [
            ("/src/auth.py", "/src/utils.py", "imports"),
            ("/jira/PROJ-1", "/src/auth.py", "references"),
            ("/a.py", "/deep/nested/path.py", "calls"),
        ]
        for s, t, c in cases:
            path = edge_out_path(s, t, c)
            parts = decompose_edge(path)
            assert parts == EdgeParts(source=s, target=t, edge_type=c, direction="out")

    def test_normalizes_target(self):
        p = edge_out_path("/a.py", "src//utils.py", "imports")
        assert p == "/.vfs/a.py/__meta__/edges/out/imports/src/utils.py"

    def test_empty_type_rejected(self):
        with pytest.raises(ValueError, match="edge_type"):
            edge_out_path("/a.py", "/b.py", "")

    def test_slash_in_type_rejected(self):
        with pytest.raises(ValueError, match="edge_type"):
            edge_out_path("/a.py", "/b.py", "calls/async")

    def test_root_target_rejected(self):
        with pytest.raises(ValueError, match="target"):
            edge_out_path("/a.py", "/", "imports")

    def test_metadata_base_rejected(self):
        with pytest.raises(ValueError, match="projected edge path"):
            edge_out_path("/.vfs/a.py/__meta__/edges/out/imports/b.py", "/c.py", "calls")

    def test_reserved_metadata_directory_endpoint_rejected(self):
        with pytest.raises(ValueError, match="reserved metadata directory"):
            edge_out_path("/a.py", "/.vfs/b.py/__meta__/edges/out", "calls")


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
# api_path
# =========================================================================


class TestApiPath:
    def test_basic(self):
        assert api_path("/jira", "ticket") == "/.vfs/jira/__meta__/apis/ticket"

    def test_roundtrip_parse_kind(self):
        assert parse_kind(api_path("/jira", "ticket")) == "api"

    def test_empty_action_rejected(self):
        with pytest.raises(ValueError, match="action"):
            api_path("/jira", "")

    def test_whitespace_action_rejected(self):
        with pytest.raises(ValueError, match="action"):
            api_path("/jira", "   ")

    def test_slash_in_action_rejected(self):
        with pytest.raises(ValueError, match="action"):
            api_path("/jira", "ticket/create")

    def test_metadata_mount_rejected(self):
        with pytest.raises(ValueError, match="metadata path"):
            api_path("/.vfs/jira/__meta__/apis", "ticket")


# =========================================================================
# validate_mutation_path
# =========================================================================


class TestValidateMutationPath:
    def test_root_is_not_mutable(self):
        assert validate_mutation_path("/") == (False, "Cannot mutate root path")

    def test_reserved_metadata_root_is_not_mutable(self):
        assert validate_mutation_path(METADATA_ROOT) == (False, "Cannot mutate reserved metadata root '/.vfs'")

    def test_inverse_edge_paths_are_read_only(self):
        valid, err = validate_mutation_path(edge_in_path("/src/a.py", "/src/b.py", "imports"))
        assert valid is False
        assert "inverse edge paths" in err

    def test_reserved_metadata_directories_are_allowed(self):
        assert validate_mutation_path("/.vfs/src/auth.py/__meta__/chunks") == (True, "")

    def test_meta_segment_directory_is_allowed(self):
        assert validate_mutation_path("/.vfs/src/auth.py/__meta__") == (True, "")

    def test_non_metadata_paths_are_mutable(self):
        assert validate_mutation_path("/src/auth.py") == (True, "")

    def test_chunk_version_and_api_paths_are_mutable(self):
        assert validate_mutation_path("/.vfs/src/auth.py/__meta__/chunks/login") == (True, "")
        assert validate_mutation_path("/.vfs/src/auth.py/__meta__/versions/3") == (True, "")
        assert validate_mutation_path("/.vfs/jira/__meta__/apis/ticket") == (True, "")

    def test_outbound_edge_paths_are_mutable(self):
        assert validate_mutation_path(edge_out_path("/src/a.py", "/src/b.py", "imports")) == (True, "")

    def test_non_reserved_meta_segment_suffix_is_allowed(self):
        assert validate_mutation_path("/.vfs/src/auth.py/custom/__meta__") == (True, "")

    def test_arbitrary_content_in_reserved_metadata_space_is_rejected(self):
        valid, err = validate_mutation_path("/.vfs/src/auth.py/random.txt")
        assert valid is False
        assert "reserved metadata space" in err

    def test_unrecognized_reserved_metadata_child_is_rejected(self):
        valid, err = validate_mutation_path("/.vfs/src/auth.py/__meta__/unknown/item")
        assert valid is False
        assert "reserved metadata space" in err


# =========================================================================
# Derived constants
# =========================================================================


class TestConstants:
    def test_metadata_kind_map_uses_canonical_families(self):
        assert METADATA_KIND_MAP == {
            "chunks": "chunk",
            "versions": "version",
            "edges": "edge",
            "apis": "api",
        }

    def test_marker_kinds_cover_projected_metadata_markers(self):
        assert MARKER_KINDS["/__meta__/chunks/"] == "chunk"
        assert MARKER_KINDS["/__meta__/versions/"] == "version"
        assert MARKER_KINDS["/__meta__/edges/out/"] == "edge"
        assert MARKER_KINDS["/__meta__/edges/in/"] == "edge"
        assert MARKER_KINDS["/__meta__/apis/"] == "api"

    def test_metadata_markers_match_marker_keys(self):
        assert tuple(MARKER_KINDS.keys()) == METADATA_MARKERS


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
# Scope / unscope helpers
# =========================================================================


class TestScopedPaths:
    def test_validate_user_id_accepts_safe_values(self):
        assert validate_user_id("alice-123") == (True, "")

    def test_validate_user_id_rejects_empty_values(self):
        assert validate_user_id("   ") == (False, "user_id must not be empty")

    def test_validate_user_id_rejects_overlong_values(self):
        assert validate_user_id("a" * 256) == (False, "user_id too long (max 255 characters)")

    def test_validate_user_id_rejects_parent_segments(self):
        assert validate_user_id("alice..ops") == (False, "user_id must not contain '..'")

    @pytest.mark.parametrize("user_id", ["al/ice", "al\\ice", "al@ice", "al\x00ice"])
    def test_validate_user_id_rejects_unsafe_characters(self, user_id):
        valid, err = validate_user_id(user_id)
        assert valid is False
        assert "unsafe character" in err

    def test_scope_root_returns_user_root(self):
        assert scope_path("/", "alice") == "/alice"

    def test_scope_non_root_prefixes_user_id(self):
        assert scope_path("/src/auth.py", "alice") == "/alice/src/auth.py"

    def test_scope_invalid_user_id_raises(self):
        with pytest.raises(ValueError, match="Invalid user_id"):
            scope_path("/src/auth.py", "alice/ops")

    def test_unscope_exact_user_root_returns_root(self):
        assert unscope_path("/alice", "alice") == "/"

    def test_unscope_outbound_edge_rewrites_both_endpoints(self):
        scoped = edge_out_path("/alice/src/a.py", "/alice/target.py", "imports")
        assert unscope_path(scoped, "alice") == edge_out_path("/src/a.py", "/target.py", "imports")

    def test_unscope_inverse_edge_rewrites_both_endpoints(self):
        scoped = edge_in_path("/alice/src/a.py", "/alice/target.py", "imports")
        assert unscope_path(scoped, "alice") == edge_in_path("/src/a.py", "/target.py", "imports")

    def test_unscope_metadata_paths_rewrites_nested_endpoint(self):
        scoped = "/.vfs/alice/src/auth.py/__meta__/chunks/login"
        assert unscope_path(scoped, "alice") == "/.vfs/src/auth.py/__meta__/chunks/login"

    def test_strip_user_prefix_rejects_mismatched_paths(self):
        with pytest.raises(ValueError, match="does not start with user prefix"):
            _strip_user_prefix("/bob/file.txt", "/alice")


# =========================================================================
# Internal helper coverage
# =========================================================================


class TestPathInternals:
    def test_metadata_root_is_classified_as_directory(self):
        assert parse_kind(METADATA_ROOT) == "directory"

    def test_metadata_tree_paths_are_classified_as_directories(self):
        assert parse_kind("/.vfs/src/auth.py") == "directory"

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
        assert _canonical_endpoint_path("/.vfs/src/auth.py/__meta__/chunks/login/body.txt") == (
            "/.vfs/src/auth.py/__meta__/chunks/login"
        )

    def test_split_nested_endpoint_returns_endpoint_when_path_stops_at_version(self):
        path = "/.vfs/src/auth.py/__meta__/versions/3"
        assert _split_nested_endpoint(path) == path

    def test_split_nested_endpoint_collapses_descendant_to_nested_root(self):
        assert _split_nested_endpoint("/.vfs/src/auth.py/__meta__/versions/3/body.txt") == (
            "/.vfs/src/auth.py/__meta__/versions/3"
        )

    def test_reserved_metadata_directory_check_is_false_for_user_paths(self):
        assert endpoint_root("/src/auth.py") == "/src/auth.py"

    def test_reserved_metadata_directory_check_is_false_outside_metadata_tree(self):
        assert _is_reserved_metadata_directory("/src/auth.py/__meta__/chunks") is False
