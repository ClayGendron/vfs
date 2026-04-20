"""Tests for query/parser.py — tokenizer, parser, builders, helpers."""

from __future__ import annotations

import pytest

from vfs.query.parser import QuerySyntaxError, parse_query, tokenize

# ===========================================================================
# Tokenizer
# ===========================================================================


class TestTokenizer:
    def test_empty_query(self):
        assert tokenize("") == ()

    def test_whitespace_only(self):
        assert tokenize("   ") == ()

    def test_pipe_token(self):
        tokens = tokenize("read /a | stat /b")
        kinds = [t.kind for t in tokens]
        assert "pipe" in kinds

    def test_amp_token(self):
        tokens = tokenize("read /a & read /b")
        kinds = [t.kind for t in tokens]
        assert "amp" in kinds

    def test_paren_tokens(self):
        tokens = tokenize("(read /a)")
        kinds = [t.kind for t in tokens]
        assert kinds[0] == "lparen"
        assert kinds[-1] == "rparen"

    def test_quoted_string(self):
        tokens = tokenize('read "hello world"')
        assert any(t.value == "hello world" and t.kind == "string" for t in tokens)

    def test_single_quoted_string(self):
        tokens = tokenize("read 'hello world'")
        assert any(t.value == "hello world" and t.kind == "string" for t in tokens)

    def test_quoted_string_with_escape(self):
        tokens = tokenize(r'read "hello\"world"')
        assert any("hello" in t.value for t in tokens if t.kind == "string")

    def test_unterminated_string(self):
        with pytest.raises(QuerySyntaxError, match="Unterminated string"):
            tokenize('read "hello')

    def test_unterminated_escape(self):
        with pytest.raises(QuerySyntaxError, match="Unterminated escape"):
            tokenize('read "hello\\')


# ===========================================================================
# Parser syntax
# ===========================================================================


class TestParserSyntax:
    def test_empty_query_raises(self):
        with pytest.raises(QuerySyntaxError, match="cannot be empty"):
            parse_query("")

    def test_unexpected_token_raises(self):
        with pytest.raises(QuerySyntaxError, match="Unexpected token"):
            parse_query("read /a )")

    def test_grouped_expression(self):
        plan = parse_query("(read /a) & (read /b)")
        assert "read" in plan.methods

    def test_intersect_subquery(self):
        plan = parse_query('glob "*.py" | intersect(glob "*.txt")')
        assert plan.ast is not None

    def test_except_subquery(self):
        plan = parse_query('glob "*.py" | except(glob "*.txt")')
        assert plan.ast is not None


# ===========================================================================
# Builder commands
# ===========================================================================


class TestBuilders:
    def test_stat(self):
        plan = parse_query("stat /a.py")
        assert plan.methods == ("stat",)

    def test_delete(self):
        plan = parse_query("rm /a.py")
        assert plan.methods == ("delete",)

    def test_edit_requires_old_and_new(self):
        with pytest.raises(QuerySyntaxError, match="edit requires old and new"):
            parse_query("edit only_one_arg")

    def test_edit_with_path(self):
        plan = parse_query("edit /a.py old new")
        assert plan.methods == ("edit",)

    def test_write_wrong_arg_count(self):
        with pytest.raises(QuerySyntaxError, match="write requires a path and content"):
            parse_query("write /a.py")

    def test_write_with_overwrite(self):
        plan = parse_query('write /a.py "content" --overwrite')
        assert plan.methods == ("write",)

    def test_write_with_no_overwrite(self):
        plan = parse_query('write /a.py "content" --no-overwrite')
        assert plan.methods == ("write",)

    def test_mkdir_no_args_raises(self):
        with pytest.raises(QuerySyntaxError, match="mkdir requires"):
            parse_query("mkdir")

    def test_mkdir_multiple_paths(self):
        plan = parse_query("mkdir /a /b /c")
        assert plan.methods == ("mkdir",)

    def test_move_one_arg(self):
        plan = parse_query("mv /dest")
        assert plan.methods == ("move",)

    def test_move_two_args(self):
        plan = parse_query("mv /src /dest")
        assert plan.methods == ("move",)

    def test_move_too_many_args(self):
        with pytest.raises(QuerySyntaxError, match="mv requires"):
            parse_query("mv /a /b /c")

    def test_copy_one_arg(self):
        plan = parse_query("cp /dest")
        assert plan.methods == ("copy",)

    def test_copy_two_args(self):
        plan = parse_query("cp /src /dest")
        assert plan.methods == ("copy",)

    def test_copy_too_many_args(self):
        with pytest.raises(QuerySyntaxError, match="cp requires"):
            parse_query("cp /a /b /c")

    def test_mkedge_two_args(self):
        plan = parse_query("mkedge imports /b.py")
        assert plan.methods == ("mkedge",)

    def test_mkedge_three_args(self):
        plan = parse_query("mkedge /a.py imports /b.py")
        assert plan.methods == ("mkedge",)

    def test_mkedge_wrong_args(self):
        with pytest.raises(QuerySyntaxError, match="mkedge requires"):
            parse_query("mkedge only_one")

    def test_glob_wrong_count(self):
        with pytest.raises(QuerySyntaxError, match="glob requires"):
            parse_query("glob")

    def test_grep_wrong_count(self):
        with pytest.raises(QuerySyntaxError, match="grep requires"):
            parse_query("grep")

    def test_grep_conflicting_case_flags(self):
        with pytest.raises(QuerySyntaxError, match="cannot combine"):
            parse_query("grep pattern --ignore-case --case-sensitive")

    def test_search(self):
        plan = parse_query('search "test query"')
        assert plan.methods == ("semantic_search",)

    def test_lsearch(self):
        plan = parse_query('lsearch "test query"')
        assert plan.methods == ("lexical_search",)

    def test_vsearch_single_bracket(self):
        plan = parse_query('vsearch "[0.1, 0.2, 0.3]"')
        assert plan.methods == ("vector_search",)

    def test_vsearch_multiple_values(self):
        plan = parse_query("vsearch 0.1 0.2 0.3")
        assert plan.methods == ("vector_search",)

    def test_meetinggraph(self):
        plan = parse_query("meetinggraph /a.py /b.py")
        assert plan.methods == ("meeting_subgraph",)

    def test_meetinggraph_minimal(self):
        plan = parse_query("meetinggraph /a.py /b.py --min")
        assert plan.methods == ("min_meeting_subgraph",)

    def test_graph_traversal_with_depth(self):
        plan = parse_query("nbr /a.py --depth 3")
        assert plan.methods == ("neighborhood",)

    def test_predecessors(self):
        plan = parse_query("pred /a.py")
        assert plan.methods == ("predecessors",)

    def test_sort_asc(self):
        plan = parse_query('glob "*.py" | sort --asc')
        assert plan.methods == ("glob", "sort")

    def test_sort_by_flag_rejected(self):
        with pytest.raises(QuerySyntaxError, match=r"Unknown flag: --by"):
            parse_query('glob "*.py" | sort --by score')

    def test_sort_positional_rejected(self):
        with pytest.raises(QuerySyntaxError, match="does not accept positional arguments"):
            parse_query('glob "*.py" | sort score')

    def test_sort_too_many_positionals(self):
        with pytest.raises(QuerySyntaxError, match="does not accept positional arguments"):
            parse_query('glob "*.py" | sort a b')

    def test_top_wrong_count(self):
        with pytest.raises(QuerySyntaxError, match="top requires"):
            parse_query('glob "*.py" | top')

    def test_kinds_no_args(self):
        with pytest.raises(QuerySyntaxError, match="kinds requires"):
            parse_query('glob "*.py" | kinds')

    def test_kinds_valid(self):
        plan = parse_query('glob "*.py" | kinds file directory')
        assert plan.methods == ("glob", "kinds")

    def test_unknown_command(self):
        with pytest.raises(QuerySyntaxError, match="Unknown command"):
            parse_query("foobar /a")


# ===========================================================================
# Visibility / overwrite / kind parsing
# ===========================================================================


class TestVisibilityParsing:
    def test_all_flag(self):
        plan = parse_query("ls --all")
        assert plan.ast is not None

    def test_include_chunks(self):
        plan = parse_query("ls --include chunks")
        assert plan.ast is not None

    def test_all_and_include_conflict(self):
        with pytest.raises(QuerySyntaxError, match="Cannot combine --all and --include"):
            parse_query("ls --all --include file")

    def test_include_comma_separated(self):
        plan = parse_query("ls --include file,directory,chunk")
        assert plan.ast is not None

    def test_overwrite_both_conflict(self):
        with pytest.raises(QuerySyntaxError, match="Cannot combine"):
            parse_query('write /a.py "x" --overwrite --no-overwrite')


class TestKindNames:
    def test_all_valid_aliases(self):
        for name in (
            "file",
            "files",
            "dir",
            "dirs",
            "directory",
            "directories",
            "chunk",
            "chunks",
            "version",
            "versions",
            "edge",
            "edges",
            "api",
            "apis",
        ):
            plan = parse_query(f"ls --include {name}")
            assert plan.ast is not None

    def test_invalid_kind(self):
        with pytest.raises(QuerySyntaxError, match="Unknown kind"):
            parse_query("ls --include bogus")


# ===========================================================================
# Flag splitting
# ===========================================================================


class TestFlagSplitting:
    def test_unknown_flag(self):
        with pytest.raises(QuerySyntaxError, match="Unknown flag"):
            parse_query("ls --bogus")

    def test_duplicate_flag(self):
        with pytest.raises(QuerySyntaxError, match="Duplicate flag"):
            parse_query("grep pattern --ignore-case --ignore-case")

    def test_flag_requiring_value_at_end(self):
        with pytest.raises(QuerySyntaxError, match="requires a value"):
            parse_query("grep pattern --max-count")

    def test_flag_followed_by_another_flag(self):
        with pytest.raises(QuerySyntaxError, match="requires a value"):
            parse_query("tree --depth --all")


# ===========================================================================
# Additional parser edge cases
# ===========================================================================


class TestParserEdgeCases:
    def test_unexpected_token_in_args(self):
        """Line 179: non-word/string token in command args raises."""
        with pytest.raises(QuerySyntaxError, match="Unexpected token"):
            parse_query("read (")

    def test_expect_at_end_of_tokens(self):
        """Line 202: _expect when at end of tokens."""
        with pytest.raises(QuerySyntaxError, match="Expected"):
            parse_query("intersect(read /a")  # missing closing paren

    def test_expect_wrong_kind(self):
        """Line 205: _expect with wrong token kind at position."""
        with pytest.raises(QuerySyntaxError, match="at position"):
            parse_query("intersect read /a)")  # ( expected, got word

    def test_tree_too_many_paths(self):
        """Line 234: tree with >1 path."""
        with pytest.raises(QuerySyntaxError, match="at most one"):
            parse_query("tree /a /b")

    def test_search_wrong_count(self):
        """Line 321: search requires exactly one query."""
        with pytest.raises(QuerySyntaxError, match="search requires"):
            parse_query("search")

    def test_lsearch_wrong_count(self):
        """Line 331: lsearch requires exactly one query."""
        with pytest.raises(QuerySyntaxError, match="lsearch requires"):
            parse_query("lsearch")

    def test_vsearch_no_args(self):
        """Line 341: vsearch requires values."""
        with pytest.raises(QuerySyntaxError, match="vsearch requires"):
            parse_query("vsearch")

    def test_include_empty_value(self):
        """Line 552: --include with empty comma-only value."""
        with pytest.raises(QuerySyntaxError, match="--include requires"):
            parse_query('ls --include ","')

    def test_parse_int_non_integer(self):
        """Lines 595-596: _parse_int with non-integer."""
        with pytest.raises(QuerySyntaxError, match="requires an integer"):
            parse_query("top abc")


# ===========================================================================
# ripgrep-compatible grep flags
# ===========================================================================


def _grep(query: str):
    """Helper: parse a bare grep command and return the GrepCommand node."""
    from vfs.query.ast import GrepCommand

    plan = parse_query(query)
    assert isinstance(plan.ast, GrepCommand)
    return plan.ast


def _glob(query: str):
    from vfs.query.ast import GlobCommand

    plan = parse_query(query)
    assert isinstance(plan.ast, GlobCommand)
    return plan.ast


class TestGrepPositionals:
    def test_pattern_only(self):
        cmd = _grep("grep foo")
        assert cmd.pattern == "foo"
        assert cmd.paths == ()

    def test_pattern_with_one_path(self):
        cmd = _grep("grep foo src/")
        assert cmd.pattern == "foo"
        assert cmd.paths == ("src/",)

    def test_pattern_with_multiple_paths(self):
        cmd = _grep("grep foo src/ lib/ tests/")
        assert cmd.paths == ("src/", "lib/", "tests/")


class TestGrepTypeFlags:
    def test_short_type(self):
        cmd = _grep("grep foo -t py")
        assert cmd.ext == ("py", "pyi")

    def test_long_type(self):
        cmd = _grep("grep foo --type python")
        assert cmd.ext == ("py", "pyi")

    def test_repeated_type(self):
        cmd = _grep("grep foo -t py -t js")
        # python → (py, pyi); js → (js, mjs, cjs)
        assert cmd.ext == ("py", "pyi", "js", "mjs", "cjs")

    def test_type_not(self):
        cmd = _grep("grep foo -T md")
        assert cmd.ext_not == ("md", "markdown", "mdown", "mkdn")

    def test_type_and_type_not(self):
        cmd = _grep("grep foo -t py -T test")
        assert cmd.ext == ("py", "pyi")
        # "test" is not a known alias — passes through as literal
        assert cmd.ext_not == ("test",)

    def test_unknown_type_passes_through(self):
        cmd = _grep("grep foo -t mjs")
        assert cmd.ext == ("mjs",)


class TestGrepGlobFlags:
    def test_single_glob(self):
        cmd = _grep("grep foo -g '*.py'")
        assert cmd.globs == ("*.py",)
        assert cmd.globs_not == ()

    def test_negated_glob(self):
        cmd = _grep("grep foo -g '!test_*.py'")
        assert cmd.globs == ()
        assert cmd.globs_not == ("test_*.py",)

    def test_positive_and_negated_globs(self):
        cmd = _grep("grep foo -g '*.py' -g '!vendor/**'")
        assert cmd.globs == ("*.py",)
        assert cmd.globs_not == ("vendor/**",)

    def test_long_glob_flag(self):
        cmd = _grep("grep foo --glob '*.rs'")
        assert cmd.globs == ("*.rs",)

    def test_empty_glob_rejected(self):
        with pytest.raises(QuerySyntaxError, match="glob pattern cannot be empty"):
            parse_query("grep foo -g ''")


class TestGrepCaseModes:
    def test_default_sensitive(self):
        cmd = _grep("grep foo")
        assert cmd.case_mode == "sensitive"

    def test_ignore_case_short(self):
        cmd = _grep("grep foo -i")
        assert cmd.case_mode == "insensitive"

    def test_ignore_case_long(self):
        cmd = _grep("grep foo --ignore-case")
        assert cmd.case_mode == "insensitive"

    def test_smart_case(self):
        cmd = _grep("grep foo -S")
        assert cmd.case_mode == "smart"

    def test_explicit_case_sensitive(self):
        cmd = _grep("grep foo -s")
        assert cmd.case_mode == "sensitive"

    def test_mutually_exclusive_i_and_s(self):
        with pytest.raises(QuerySyntaxError, match="cannot combine"):
            parse_query("grep foo -i -s")

    def test_mutually_exclusive_i_and_smart(self):
        with pytest.raises(QuerySyntaxError, match="cannot combine"):
            parse_query("grep foo -i -S")


class TestGrepOutputModes:
    def test_default_lines(self):
        cmd = _grep("grep foo")
        assert cmd.output_mode == "lines"

    def test_files_with_matches_short(self):
        cmd = _grep("grep foo -l")
        assert cmd.output_mode == "files"

    def test_files_with_matches_long(self):
        cmd = _grep("grep foo --files-with-matches")
        assert cmd.output_mode == "files"

    def test_files_alias(self):
        cmd = _grep("grep foo --files")
        assert cmd.output_mode == "files"

    def test_count_short(self):
        cmd = _grep("grep foo -c")
        assert cmd.output_mode == "count"

    def test_files_and_count_rejected(self):
        with pytest.raises(QuerySyntaxError, match="mutually exclusive"):
            parse_query("grep foo -l -c")


class TestGrepContextFlags:
    def test_context_c(self):
        cmd = _grep("grep foo -C 3")
        assert cmd.before_context == 3
        assert cmd.after_context == 3

    def test_context_long(self):
        cmd = _grep("grep foo --context 5")
        assert cmd.before_context == 5
        assert cmd.after_context == 5

    def test_before_only(self):
        cmd = _grep("grep foo -B 2")
        assert cmd.before_context == 2
        assert cmd.after_context == 0

    def test_after_only(self):
        cmd = _grep("grep foo -A 4")
        assert cmd.before_context == 0
        assert cmd.after_context == 4

    def test_before_after_override_context(self):
        cmd = _grep("grep foo -C 3 -B 1 -A 5")
        assert cmd.before_context == 1
        assert cmd.after_context == 5


class TestGrepPatternFlags:
    def test_fixed_strings(self):
        cmd = _grep("grep foo -F")
        assert cmd.fixed_strings is True

    def test_word_regexp(self):
        cmd = _grep("grep foo -w")
        assert cmd.word_regexp is True

    def test_invert_match(self):
        cmd = _grep("grep foo -v")
        assert cmd.invert_match is True


class TestGrepLimits:
    def test_max_count_short(self):
        cmd = _grep("grep foo -m 50")
        assert cmd.max_count == 50

    def test_max_count_long(self):
        cmd = _grep("grep foo --max-count 100")
        assert cmd.max_count == 100

    def test_max_results_removed(self):
        with pytest.raises(QuerySyntaxError, match="Unknown flag"):
            parse_query("grep foo --max-results 20")


class TestGrepNoOpCompat:
    """rg compat flags that VFS accepts but does not act on."""

    def test_hidden(self):
        cmd = _grep("grep foo --hidden")
        assert cmd.pattern == "foo"

    def test_no_ignore(self):
        cmd = _grep("grep foo --no-ignore")
        assert cmd.pattern == "foo"

    def test_follow(self):
        cmd = _grep("grep foo --follow")
        assert cmd.pattern == "foo"


class TestGrepCombined:
    def test_kitchen_sink(self):
        cmd = _grep("grep 'login' src/ lib/ -t py -t js -g '*.test.*' -g '!vendor/**' -i -F -w -C 3 -m 50 -l")
        assert cmd.pattern == "login"
        assert cmd.paths == ("src/", "lib/")
        assert cmd.ext == ("py", "pyi", "js", "mjs", "cjs")
        assert cmd.globs == ("*.test.*",)
        assert cmd.globs_not == ("vendor/**",)
        assert cmd.case_mode == "insensitive"
        assert cmd.fixed_strings is True
        assert cmd.word_regexp is True
        assert cmd.before_context == 3
        assert cmd.after_context == 3
        assert cmd.max_count == 50
        assert cmd.output_mode == "files"


# ===========================================================================
# ripgrep-compatible glob command
# ===========================================================================


class TestGlobPositionals:
    def test_pattern_only(self):
        cmd = _glob("glob '*.py'")
        assert cmd.pattern == "*.py"
        assert cmd.paths == ()

    def test_pattern_with_paths(self):
        cmd = _glob("glob '**/*.py' src/ tests/")
        assert cmd.pattern == "**/*.py"
        assert cmd.paths == ("src/", "tests/")


class TestGlobFlags:
    def test_type_filter(self):
        cmd = _glob("glob '**' -t py")
        assert cmd.ext == ("py", "pyi")

    def test_max_count(self):
        cmd = _glob("glob '**/*.py' -m 100")
        assert cmd.max_count == 100


# ===========================================================================
# Flag parser internals — short flags, repeats, unknown flags
# ===========================================================================


class TestFlagParsing:
    def test_short_flag_not_in_spec_treated_as_positional(self):
        # `-3` is not a flag for grep — passes through as a positional path.
        cmd = _grep("grep foo -3")
        assert cmd.paths == ("-3",)

    def test_unknown_long_flag_rejected(self):
        with pytest.raises(QuerySyntaxError, match="Unknown flag"):
            parse_query("grep foo --nonsense")

    def test_repeat_non_repeatable_flag_rejected(self):
        with pytest.raises(QuerySyntaxError, match="Duplicate flag"):
            parse_query("grep foo -i -i")

    def test_flag_requires_value(self):
        with pytest.raises(QuerySyntaxError, match="requires a value"):
            parse_query("grep foo -t")


class TestOutputFlag:
    def test_no_output_means_none(self):
        plan = parse_query("glob /a")
        assert plan.projection is None

    def test_output_two_token_form(self):
        plan = parse_query("glob /a --output path,score")
        assert plan.projection == ("path", "score")

    def test_output_equals_form(self):
        plan = parse_query("glob /a --output=path,score")
        assert plan.projection == ("path", "score")

    def test_output_at_pipeline_end(self):
        plan = parse_query("glob /a | sort --output path,updated_at")
        assert plan.projection == ("path", "updated_at")

    def test_output_strips_whitespace(self):
        plan = parse_query("glob /a --output 'path, score, kind'")
        assert plan.projection == ("path", "score", "kind")

    def test_output_supports_default_sentinel(self):
        plan = parse_query("glob /a --output default")
        assert plan.projection == ("default",)

    def test_output_supports_all_sentinel(self):
        plan = parse_query("glob /a --output all")
        assert plan.projection == ("all",)

    def test_output_unknown_field_rejected(self):
        with pytest.raises(QuerySyntaxError, match="unknown field 'bogus'"):
            parse_query("glob /a --output path,bogus")

    def test_output_repeated_rejected(self):
        with pytest.raises(QuerySyntaxError, match="only be specified once"):
            parse_query("glob /a --output path --output kind")

    def test_output_requires_value(self):
        with pytest.raises(QuerySyntaxError, match="requires a value"):
            parse_query("glob /a --output")

    def test_output_empty_value_rejected(self):
        with pytest.raises(QuerySyntaxError, match="at least one field"):
            parse_query("glob /a --output ''")

    def test_output_leaves_non_output_args_intact(self):
        plan = parse_query("grep foo --output path -i")
        # The grep flag (-i case-insensitive) stays attached to the GrepCommand.
        from vfs.query.ast import GrepCommand, PipelineNode

        ast = plan.ast
        cmd = ast.source if isinstance(ast, PipelineNode) else ast
        assert isinstance(cmd, GrepCommand)
        assert cmd.case_mode == "insensitive"
        assert plan.projection == ("path",)
