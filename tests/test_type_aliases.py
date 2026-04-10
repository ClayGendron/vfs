"""Tests for grover.query.types — ripgrep-style type alias resolution."""

from __future__ import annotations

from grover.query.types import TYPE_ALIASES, resolve_type_aliases


class TestResolveTypeAliases:
    def test_known_alias(self):
        assert resolve_type_aliases(("python",)) == ("py", "pyi")

    def test_bare_extension_passes_through(self):
        assert resolve_type_aliases(("py",)) == ("py", "pyi")

    def test_unknown_alias_treated_as_literal(self):
        assert resolve_type_aliases(("mjs",)) == ("mjs",)

    def test_mixed_alias_and_literal(self):
        # "python" expands; "mjs" is literal
        result = resolve_type_aliases(("python", "mjs"))
        assert result == ("py", "pyi", "mjs")

    def test_duplicates_removed_preserving_order(self):
        # python → (py, pyi); then explicit py is deduped
        result = resolve_type_aliases(("python", "py"))
        assert result == ("py", "pyi")

    def test_multiple_aliases(self):
        result = resolve_type_aliases(("python", "js"))
        assert result == ("py", "pyi", "js", "mjs", "cjs")

    def test_case_insensitive_alias_lookup(self):
        assert resolve_type_aliases(("Python",)) == ("py", "pyi")
        assert resolve_type_aliases(("PY",)) == ("py", "pyi")

    def test_empty_input(self):
        assert resolve_type_aliases(()) == ()

    def test_typescript_alias(self):
        assert resolve_type_aliases(("typescript",)) == ("ts", "tsx")

    def test_rust_alias(self):
        assert resolve_type_aliases(("rust",)) == ("rs",)

    def test_yaml_alias(self):
        assert resolve_type_aliases(("yaml",)) == ("yaml", "yml")

    def test_cpp_alias_covers_headers(self):
        result = resolve_type_aliases(("cpp",))
        assert "cpp" in result
        assert "h" in result
        assert "hpp" in result


class TestTypeAliasesTable:
    def test_all_values_are_lowercase(self):
        for name, exts in TYPE_ALIASES.items():
            for ext in exts:
                # The table is case-sensitive on the key side (lowercase is
                # enforced at lookup), but values should also be lowercase
                # to avoid surprises in the index query.
                assert ext == ext.lower() or name == "r", f"{name}: extension {ext!r} should be lowercase"

    def test_common_languages_present(self):
        for alias in ("python", "js", "ts", "go", "rust", "java", "md", "yaml", "sql"):
            assert alias in TYPE_ALIASES, f"missing alias: {alias}"
