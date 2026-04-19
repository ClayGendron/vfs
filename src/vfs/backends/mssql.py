"""MSSQLFileSystem — SQL Server / Azure SQL backend with full-text and regex pushdown.

Subclass of :class:`DatabaseFileSystem` that overrides the three search
methods (``_lexical_search_impl``, ``_grep_impl``, ``_glob_impl``) to push
work into SQL Server 2025+ / current Azure SQL Database, where it scales
to corpora well past 1 million rows.

Why this exists: the base ``DatabaseFileSystem`` implementations either
ship every file's content over the wire and run regex/BM25 in Python
(grep, lexical_search) or post-filter in Python after a coarse SQL pre-
filter (glob).  At MSSQL scale we can do better — Full-Text Search has
an inverted index, ``CONTAINSTABLE`` returns BM25-style ranks server-
side, and SQL Server 2025 ships a native ``REGEXP_LIKE`` predicate that
runs row-level on the server.

Schema responsibility: this class does **not** create catalogs, indexes,
or full-text artifacts.  It assumes the database administrator (or
deployment tooling) has already provisioned them on the same schema as
the SQLAlchemy engine resolves to.  Call :meth:`verify_fulltext_schema`
at app startup to fail fast on a misconfigured database.

Requires SQL Server 2025 RTM or current Azure SQL Database.  No fallback
for older versions.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, ClassVar

from sqlalchemy import text

from vfs.backends.database import (
    DatabaseFileSystem,
    _compile_grep_regex,
    _escape_like,
    _regex_flags_for_mode,
)
from vfs.bm25 import tokenize_query
from vfs.paths import scope_path
from vfs.patterns import compile_glob, decompose_glob, glob_to_sql_like
from vfs.results import Entry, VFSResult

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from vfs.query.ast import CaseMode, GrepOutputMode


# ---------------------------------------------------------------------------
# Literal-term extraction for grep pre-filter
# ---------------------------------------------------------------------------


def _extract_literal_terms(pattern: str) -> list[str]:
    """Extract guaranteed-literal alphanumeric runs from a regex.

    Used to coarse-pre-filter via SQL Server Full-Text ``CONTAINS`` before
    running ``REGEXP_LIKE`` on the narrowed result set.  Conservative —
    bails out (returns ``[]``) for patterns where extraction would be
    unsound, namely:

    - any quantified group: ``(...)?``, ``(...)*``, ``(...)+``, ``(...){…}``
    - any top-level alternation: ``foo|bar`` (the literal "foo" is not
      guaranteed to appear in matches; an alternation cannot become an
      AND-of-CONTAINS pre-filter without changing semantics)

    For acceptable patterns, strips escapes, character classes, group
    parens, and quantified word-chars, then returns up to 8 unique runs
    of length ≥ 3.  These are AND'd into a CONTAINS expression.
    """
    # Bail on quantified groups: (...)?  (...)*  (...)+  (...){...}
    if re.search(r"\)[*+?{]", pattern):
        return []
    # Bail on alternation outside a character class.
    stripped_for_alt = re.sub(r"\\.", "", pattern)
    stripped_for_alt = re.sub(r"\[[^\]]*\]", "", stripped_for_alt)
    if "|" in stripped_for_alt:
        return []

    cleaned = re.sub(r"\\.", " ", pattern)  # drop escapes (incl. \w \d \( etc.)
    cleaned = re.sub(r"\[[^\]]*\]", " ", cleaned)  # drop character classes
    cleaned = cleaned.replace("(", " ").replace(")", " ")  # drop bare group parens
    cleaned = re.sub(r"\w[*+?]", " ", cleaned)  # drop quantified single chars
    cleaned = re.sub(r"\w\{[^}]*\}", " ", cleaned)  # drop {n,m}-quantified chars
    cleaned = re.sub(r"[.^$]", " ", cleaned)  # drop anchors and dot

    runs = re.findall(r"[A-Za-z0-9_]{3,}", cleaned)
    seen: set[str] = set()
    out: list[str] = []
    for run in runs:
        if run not in seen:
            seen.add(run)
            out.append(run)
            if len(out) >= 8:
                break
    return out


def _quote_contains_term(term: str) -> str:
    """Wrap a term in double quotes for a CONTAINS expression, escaping any embedded quotes."""
    return '"' + term.replace('"', '""') + '"'


class MSSQLFileSystem(DatabaseFileSystem):
    """SQL Server / Azure SQL backend with full-text search and native regex pushdown.

    Inherits CRUD, versions, chunks, connections, graph, and vector
    search unchanged from :class:`DatabaseFileSystem`.  Only the three
    search entry points are overridden.

    The class assumes the connection's default schema already contains
    the ``VFSObject`` table and a full-text index on its ``content``
    column.  Use :meth:`verify_fulltext_schema` at startup to confirm.

    Lexical search and grep operate on **files only** — versions and
    chunks are excluded.  Glob still includes directories.
    """

    FULLTEXT_TOP_N: ClassVar[int] = 1_000  # CONTAINSTABLE top_n_by_rank cap

    # ------------------------------------------------------------------
    # Schema resolution
    # ------------------------------------------------------------------

    def _resolve_table(self) -> str:
        """Return the schema-qualified table name for raw ``text()`` SQL.

        Raw ``text()`` SQL bypasses SQLAlchemy's schema rewriting — the
        ORM only applies ``schema_translate_map`` when compiling
        ``Table`` references, not to opaque string SQL.  This helper
        qualifies the bare ``__tablename__`` with ``self._schema`` (set
        on ``VirtualFileSystem`` at init time) so raw queries resolve to
        the same table the ORM would hit for this filesystem.

        Returns the bare ``__tablename__`` when no schema is configured,
        letting the connection's default schema take over — this
        matches the pre-schema behaviour and keeps existing mounts
        working.
        """
        table = str(self._model.__tablename__)
        return f"{self._schema}.{table}" if self._schema else table

    # ------------------------------------------------------------------
    # Schema verification
    # ------------------------------------------------------------------

    async def verify_fulltext_schema(self) -> None:
        """Confirm the database has the schema required for fast search.

        Raises ``RuntimeError`` if any requirement is missing.  Call this
        once at app startup to fail fast on a misconfigured database.
        Does **not** create or alter any objects.

        Requirements:

        1. The ``VFSObject`` table is resolvable in the connection's
           default schema (i.e. ``OBJECT_ID(N'<tablename>')`` is non-null).
        2. A ``content`` column exists on the table.
        3. A full-text index exists on that ``content`` column.
        """
        table = self._resolve_table()
        bare_table = self._model.__tablename__
        async with self._use_session() as session:
            object_id = (await session.execute(text(f"SELECT OBJECT_ID(N'{table}') AS oid"))).scalar()
            if object_id is None:
                raise RuntimeError(
                    f"MSSQLFileSystem requires table '{table}' to exist. Run "
                    f"SQLModel.metadata.create_all first or grant access to the "
                    f"existing table."
                )

            content_column_exists = (
                await session.execute(
                    text("SELECT 1 FROM sys.columns WHERE object_id = :oid AND name = 'content'"),
                    {"oid": object_id},
                )
            ).scalar()
            if content_column_exists is None:
                raise RuntimeError(f"MSSQLFileSystem requires a 'content' column on '{table}'.")

            fulltext_index_exists = (
                await session.execute(
                    text(
                        "SELECT 1 "
                        "FROM sys.fulltext_index_columns AS fic "
                        "INNER JOIN sys.columns AS c "
                        "  ON fic.object_id = c.object_id AND fic.column_id = c.column_id "
                        "WHERE fic.object_id = :oid AND c.name = 'content'"
                    ),
                    {"oid": object_id},
                )
            ).scalar()
            if fulltext_index_exists is None:
                raise RuntimeError(
                    f"MSSQLFileSystem requires a SQL Server Full-Text index on "
                    f"'{table}.content'. Provision one outside the application, "
                    f"for example:\n"
                    f"  CREATE FULLTEXT CATALOG vfs_ftcat;\n"
                    f"  CREATE UNIQUE NONCLUSTERED INDEX ux_{bare_table}_id "
                    f"ON {table}(id);\n"
                    f"  CREATE FULLTEXT INDEX ON {table}(content LANGUAGE 1033)\n"
                    f"  KEY INDEX ux_{bare_table}_id\n"
                    f"  ON vfs_ftcat WITH CHANGE_TRACKING AUTO;"
                )

    # ------------------------------------------------------------------
    # Lexical search — CONTAINSTABLE pushdown (files only)
    # ------------------------------------------------------------------

    async def _lexical_search_impl(
        self,
        query: str,
        k: int = 15,
        candidates: VFSResult | None = None,
        *,
        user_id: str | None = None,
        session: AsyncSession,
    ) -> VFSResult:
        """BM25-style lexical search via SQL Server Full-Text ``CONTAINSTABLE``.

        Replaces the base class's SQL-LIKE pre-filter + Python BM25 with
        a single round trip:

        - Tokenize *query* (capped at 50 terms by ``tokenize_query``).
        - Build a ``("t1" OR "t2" OR …)`` CONTAINS expression.
        - Issue ``CONTAINSTABLE(content, expr, top_n_by_rank)`` joined back
          to the table for live files only.
        - Sort by ``ct.[RANK]`` server-side, return top *k*.

        Why this scales past 1M rows:

        - Full-text inverted index (not a table scan) locates matches.
        - ``top_n_by_rank`` caps the rows the engine ranks.
        - Only ``path``, ``kind``, and ``RANK`` cross the wire — content
          stays on the server.

        Operates on files only; chunks and versions are excluded.

        When *candidates* is passed, MSSQL has nothing to add — the
        candidate set is already in Python and (after the hydration
        changes) carries content, so the base class runs BM25 in Python
        without any round trip.
        """
        # Candidates path: delegate to base class so already-hydrated
        # content drives BM25 in Python with zero SQL.
        if candidates is not None:
            return await super()._lexical_search_impl(
                query,
                k=k,
                candidates=candidates,
                user_id=user_id,
                session=session,
            )

        self._require_user_id(user_id)
        if not query or not query.strip():
            return self._error("lexical_search requires a query")

        terms = tokenize_query(query)
        if not terms:
            return self._error("lexical_search: no searchable terms in query")
        unique_terms = list(dict.fromkeys(terms))
        contains_expr = " OR ".join(_quote_contains_term(t) for t in unique_terms)

        table = self._resolve_table()
        top_n = max(k * 4, self.FULLTEXT_TOP_N)
        user_scope_clause = ""
        params_base: dict[str, object] = {"expr": contains_expr, "top_n": top_n}
        if self._user_scoped and user_id:
            user_scope_clause = " AND o.path LIKE :user_scope ESCAPE '\\'"
            params_base["user_scope"] = f"/{user_id}/%"

        sql = text(f"""
            SELECT TOP (:k) o.path, o.kind, ct.[RANK] AS score
            FROM CONTAINSTABLE({table}, content, :expr, :top_n) AS ct
            INNER JOIN {table} AS o ON o.id = ct.[KEY]
            WHERE o.kind = 'file'
              AND o.deleted_at IS NULL
              {user_scope_clause}
            ORDER BY ct.[RANK] DESC
        """)
        params = {**params_base, "k": k}
        rows = (await session.execute(sql, params)).all()

        # Hydrate content for the (small) top-k result set so downstream
        # stages don't have to re-query.  k is bounded (default 15), so
        # this is a single small batched read.
        scored_paths = [(row.path, row.kind, float(row.score)) for row in rows]
        content_by_path: dict[str, str | None] = {}
        if scored_paths:
            top_paths = [path for path, _kind, _score in scored_paths]
            content_sql = text(f"""
                SELECT path, content
                FROM {table}
                WHERE path IN ({", ".join(f":p{i}" for i in range(len(top_paths)))})
                  AND deleted_at IS NULL
            """)
            content_params: dict[str, object] = {f"p{i}": p for i, p in enumerate(top_paths)}
            content_rows = (await session.execute(content_sql, content_params)).all()
            content_by_path = {r.path: r.content for r in content_rows}

        result = VFSResult(
            function="lexical_search",
            entries=[
                Entry(
                    path=path,
                    kind=kind,
                    content=content_by_path.get(path),
                    score=score,
                )
                for path, kind, score in scored_paths
            ],
        )
        return self._unscope_result(result, user_id)

    # ------------------------------------------------------------------
    # Grep — REGEXP_LIKE pushdown with optional CONTAINS pre-filter
    # ------------------------------------------------------------------

    def _build_grep_structural_sql(
        self,
        *,
        ext: tuple[str, ...],
        ext_not: tuple[str, ...],
        paths: tuple[str, ...],
        globs: tuple[str, ...],
        globs_not: tuple[str, ...],
        user_id: str | None,
        alias: str = "o",
    ) -> tuple[str, dict[str, object]]:
        """Compose the rg-structural filter clauses for grep/glob SQL.

        Returns ``(clause_sql, params)`` where *clause_sql* is a string
        ready to be appended after an existing ``WHERE …`` (each clause
        is pre-joined with ``AND`` and the whole string starts with a
        leading ``AND `` when non-empty).  All column references use the
        supplied *alias*.

        Positive ``globs`` push an authoritative ``REGEXP_LIKE(path, …)``
        alongside the sargable ``LIKE`` pre-filter so the engine can
        seek on a literal prefix and still reject LIKE over-matches
        server-side.  ``globs_not`` uses ``NOT REGEXP_LIKE`` only —
        there is no sargable form for negation.
        """
        clauses: list[str] = []
        params: dict[str, object] = {}
        col = f"{alias}.path" if alias else "path"
        ext_col = f"{alias}.ext" if alias else "ext"

        if self._user_scoped and user_id:
            clauses.append(f"{col} LIKE :user_scope ESCAPE '\\'")
            params["user_scope"] = f"/{user_id}/%"

        if ext:
            in_list = ", ".join(f":gext{i}" for i in range(len(ext)))
            clauses.append(f"{ext_col} IN ({in_list})")
            for i, e in enumerate(ext):
                params[f"gext{i}"] = e

        if ext_not:
            in_list = ", ".join(f":gextn{i}" for i in range(len(ext_not)))
            clauses.append(f"{ext_col} NOT IN ({in_list})")
            for i, e in enumerate(ext_not):
                params[f"gextn{i}"] = e

        if paths:
            path_or: list[str] = []
            for i, raw in enumerate(paths):
                prefix = self._scope_filter_prefix(raw, user_id).rstrip("/") or "/"
                path_or.append(f"{col} = :gpeq{i} OR {col} LIKE :gppre{i} ESCAPE '\\'")
                params[f"gpeq{i}"] = prefix
                params[f"gppre{i}"] = _escape_like(prefix) + "/%"
            clauses.append("(" + " OR ".join(path_or) + ")")

        if globs:
            glob_or: list[str] = []
            for i, raw in enumerate(globs):
                scoped = self._scope_filter_prefix(raw, user_id)
                regex = compile_glob(scoped)
                if regex is None:
                    continue
                like = glob_to_sql_like(scoped)
                if like is not None:
                    glob_or.append(f"({col} LIKE :ggl{i} ESCAPE '\\' AND REGEXP_LIKE({col}, :ggr{i}, 'c'))")
                    params[f"ggl{i}"] = like
                else:
                    glob_or.append(f"REGEXP_LIKE({col}, :ggr{i}, 'c')")
                params[f"ggr{i}"] = regex.pattern
            if glob_or:
                clauses.append("(" + " OR ".join(glob_or) + ")")

        if globs_not:
            for i, raw in enumerate(globs_not):
                scoped = self._scope_filter_prefix(raw, user_id)
                regex = compile_glob(scoped)
                if regex is None:
                    continue
                clauses.append(f"NOT REGEXP_LIKE({col}, :ggnr{i}, 'c')")
                params[f"ggnr{i}"] = regex.pattern

        if not clauses:
            return "", params
        return " AND " + " AND ".join(clauses), params

    async def _grep_impl(
        self,
        pattern: str,
        *,
        paths: tuple[str, ...] = (),
        ext: tuple[str, ...] = (),
        ext_not: tuple[str, ...] = (),
        globs: tuple[str, ...] = (),
        globs_not: tuple[str, ...] = (),
        case_mode: CaseMode = "sensitive",
        fixed_strings: bool = False,
        word_regexp: bool = False,
        invert_match: bool = False,
        before_context: int = 0,
        after_context: int = 0,
        output_mode: GrepOutputMode = "lines",
        max_count: int | None = None,
        columns: frozenset[str] | None = None,
        candidates: VFSResult | None = None,
        user_id: str | None = None,
        session: AsyncSession,
    ) -> VFSResult:
        """Regex content search pushed into SQL via ``REGEXP_LIKE``.

        Operates on files only; chunks and versions are excluded.

        Four SQL templates, picked by ``output_mode`` and whether a
        Full-Text literal pre-filter is extractable:

        1. **CONTAINSTABLE + lines** — when literal terms can be mined
           from the regex and the caller wants per-line detail.
        2. **CONTAINSTABLE + files** — same pre-filter, but ``-l`` /
           ``--files-with-matches``: ``SELECT`` the path only, no
           content transfer.
        3. **Direct + lines** — pure character-class / alternation
           patterns with no literal runs; ``REGEXP_LIKE`` drives the
           scan under ``MAXDOP 1``.
        4. **Direct + files** — same direct path, path-only projection.

        Structural filters (``ext``, ``paths``, ``globs`` / ``globs_not``)
        compose onto all four via :meth:`_build_grep_structural_sql`.
        ``ext`` seeks the ``ix_vfs_objects_ext_kind`` composite
        index, so ``-t py`` on a 1M-row corpus narrows before the
        regex engine runs.

        ``invert_match`` (``-v``) disables both pushdowns — the match
        predicate inverts per line, so the server cannot pre-filter on
        "content contains pattern".  Content for the structural-filter
        result set is streamed back and scanned client-side.

        ``REGEXP_LIKE`` has a 2 MB LOB ceiling — only the first ~1M
        characters of an ``nvarchar(max)`` value are scanned.  For
        typical source code and docs this never matters.
        """
        # When candidates are supplied they already carry content (after
        # the hydration changes), so MSSQL has nothing to add — the base
        # class runs the regex in Python without a round trip.
        if candidates is not None:
            return await super()._grep_impl(
                pattern,
                paths=paths,
                ext=ext,
                ext_not=ext_not,
                globs=globs,
                globs_not=globs_not,
                case_mode=case_mode,
                fixed_strings=fixed_strings,
                word_regexp=word_regexp,
                invert_match=invert_match,
                before_context=before_context,
                after_context=after_context,
                output_mode=output_mode,
                max_count=max_count,
                columns=columns,
                candidates=candidates,
                user_id=user_id,
                session=session,
            )

        cols = self._resolve_columns("grep", columns) | {"content"}

        self._require_user_id(user_id)
        if not pattern:
            return self._error("grep requires a pattern")

        try:
            regex = _compile_grep_regex(
                pattern,
                case_mode=case_mode,
                fixed_strings=fixed_strings,
                word_regexp=word_regexp,
            )
        except re.error as exc:
            return self._error(f"Invalid regex pattern: {exc}")

        effective_pattern = regex.pattern
        flags = _regex_flags_for_mode(case_mode, pattern)
        # Always include 'm' (multi-line) so ^/$ match at line
        # boundaries — matches per-line Python grep and grep(1)
        # conventions.  Without 'm', REGEXP_LIKE treats ^/$ as
        # start/end-of-string only.
        sql_flags = "im" if flags & re.IGNORECASE else "cm"
        table = self._resolve_table()

        filter_clause, filter_params = self._build_grep_structural_sql(
            ext=ext,
            ext_not=ext_not,
            paths=paths,
            globs=globs,
            globs_not=globs_not,
            user_id=user_id,
            alias="o",
        )

        params: dict[str, object] = dict(filter_params)
        top_clause = ""
        if max_count is not None:
            top_clause = "TOP (:max_count) "
            params["max_count"] = max_count

        # Path-only projection is only safe when the regex predicate is
        # in SQL and guarantees a match — i.e. not inverted and caller
        # only wants -l.  Lines/count modes need content for the client-
        # side line scan; widen the SELECT to the user's projected cols
        # so each row carries everything the entries need in one trip.
        files_only = output_mode == "files" and not invert_match
        if files_only:
            select_set: frozenset[str] = frozenset({"path"})
        else:
            select_set = cols | {"content"}
        select_cols = ", ".join(f"o.{c}" for c in sorted(select_set))
        content_not_null = "" if files_only else "AND o.content IS NOT NULL"

        regex_clause = ""
        if not invert_match:
            regex_clause = "AND REGEXP_LIKE(o.content, :pattern, CAST(:flags AS VARCHAR(4)))"
            params["pattern"] = effective_pattern
            params["flags"] = sql_flags

        literal_terms = _extract_literal_terms(effective_pattern) if not invert_match else []
        if literal_terms:
            contains_expr = " AND ".join(_quote_contains_term(t) for t in literal_terms)
            params["expr"] = contains_expr
            sql = text(f"""
                SELECT {top_clause}{select_cols}
                FROM CONTAINSTABLE({table}, content, :expr) AS ct
                INNER JOIN {table} AS o ON o.id = ct.[KEY]
                WHERE o.kind = 'file'
                  AND o.deleted_at IS NULL
                  {content_not_null}
                  {regex_clause}
                  {filter_clause}
                ORDER BY ct.[RANK] DESC
            """)
        else:
            sql = text(f"""
                SELECT {top_clause}{select_cols}
                FROM {table} AS o
                WHERE o.kind = 'file'
                  AND o.deleted_at IS NULL
                  {content_not_null}
                  {regex_clause}
                  {filter_clause}
                ORDER BY o.path
                OPTION (MAXDOP 1)
            """)

        rows = (await session.execute(sql, params)).all()

        if files_only:
            # Files-only mode: regex predicate runs in SQL, every row is a
            # guaranteed hit.  Entries carry path + kind (kind hardcoded
            # because the WHERE clause already filtered to ``kind='file'``);
            # any wider projection backfills via hydration since we didn't
            # SELECT it here.
            matched = [Entry(path=row.path, kind="file") for row in rows]
            return self._unscope_result(VFSResult(function="grep", entries=matched), user_id)

        # Lines/count modes: rows carry content + every projected col, so
        # _collect_line_matches builds entries directly from real rows via
        # _row_to_entry — no SimpleNamespace stand-ins, no hydration round
        # trip for cols we already selected.
        rows_by_path = {row.path: row for row in rows if row.content}
        matched = self._collect_line_matches(
            rows_by_path,
            cols,
            regex,
            max_count,
            output_mode=output_mode,
            before_context=before_context,
            after_context=after_context,
            invert_match=invert_match,
        )
        return self._unscope_result(VFSResult(function="grep", entries=matched), user_id)

    # ------------------------------------------------------------------
    # Glob — REGEXP_LIKE pushdown on path
    # ------------------------------------------------------------------

    async def _glob_impl(
        self,
        pattern: str,
        *,
        paths: tuple[str, ...] = (),
        ext: tuple[str, ...] = (),
        max_count: int | None = None,
        columns: frozenset[str] | None = None,
        candidates: VFSResult | None = None,
        user_id: str | None = None,
        session: AsyncSession,
    ) -> VFSResult:
        """Glob match with the authoritative regex pushed into SQL.

        Keeps the SARGable ``LIKE`` pre-filter (so a leading literal
        prefix can drive an index seek) and adds
        ``REGEXP_LIKE(path, :glob_regex, 'c')`` as the authoritative
        gate — no Python post-filter, sort moves into SQL via
        ``ORDER BY path``.

        Extends the base-class signature with rg-style ``ext`` and
        positional ``paths`` pushdowns composed via
        :meth:`_build_grep_structural_sql`.  ``compile_glob`` produces
        plain POSIX-style regexes so the regex source passes straight
        into ``REGEXP_LIKE``.  The 2 MB LOB ceiling does not apply to
        the ``path`` column.
        """
        # When candidates are supplied they already carry content (after
        # the hydration changes), so MSSQL has nothing to add — the base
        # class filters in Python without a round trip.
        if candidates is not None:
            return await super()._glob_impl(
                pattern,
                paths=paths,
                ext=ext,
                max_count=max_count,
                columns=columns,
                candidates=candidates,
                user_id=user_id,
                session=session,
            )

        cols = self._resolve_columns("glob", columns)
        self._require_user_id(user_id)
        unscoped_pattern = pattern
        if self._user_scoped and user_id:
            pattern = scope_path(pattern, user_id) if pattern.startswith("/") else f"/{user_id}/{pattern}"
        if not pattern:
            return self._error("glob requires a pattern")

        regex = compile_glob(pattern)
        if regex is None:
            return self._error(f"Invalid glob pattern: {pattern}")

        # Decompose the *unscoped* pattern: merged_paths flows through
        # _build_grep_structural_sql which re-scopes via
        # _scope_filter_prefix, so passing a pre-scoped prefix would
        # double-scope.
        decomposition = decompose_glob(unscoped_pattern)

        # Merge the glob's implicit ext with the caller's explicit ext.
        # Caller-supplied ext is authoritative: if the intersection is
        # empty, short-circuit to an empty result.
        merged_ext: tuple[str, ...]
        if ext and decomposition.ext:
            merged_ext = tuple(e for e in ext if e in decomposition.ext)
            if not merged_ext:
                return self._unscope_result(VFSResult(function="glob", entries=[]), user_id)
        elif decomposition.ext:
            merged_ext = decomposition.ext
        else:
            merged_ext = ext

        # Merge the glob's prefix into paths only when the caller left
        # paths empty — caller-supplied paths are authoritative.
        merged_paths: tuple[str, ...]
        if paths:
            merged_paths = paths
        elif decomposition.prefix is not None:
            merged_paths = (decomposition.prefix,)
        else:
            merged_paths = ()

        table = self._resolve_table()
        like_pattern = glob_to_sql_like(pattern)
        like_clause = "AND path LIKE :like_pattern ESCAPE '\\'" if like_pattern is not None else ""

        filter_clause, filter_params = self._build_grep_structural_sql(
            ext=merged_ext,
            ext_not=(),
            paths=merged_paths,
            globs=(),
            globs_not=(),
            user_id=user_id,
            alias="",
        )

        params: dict[str, object] = {**filter_params}
        top_clause = ""
        if max_count is not None:
            top_clause = "TOP (:max_count) "
            params["max_count"] = max_count
        if like_pattern is not None:
            params["like_pattern"] = like_pattern

        if decomposition.residual_regex is not None:
            # Use the scoped regex so it matches the scoped path column;
            # decomposition.residual_regex is compiled from the unscoped
            # pattern and only indicates whether a residual is *needed*.
            params["glob_regex"] = regex.pattern
            regex_clause = "AND REGEXP_LIKE(path, :glob_regex, 'c')"
            kind_clause = "kind IN ('file', 'directory')"
        else:
            regex_clause = ""
            # ext IS NULL on directory rows, so ext IN (…) already excludes
            # directories — narrow kind explicitly to make the plan seek
            # ix_vfs_objects_ext_kind rather than rely on a NULL side
            # effect.
            kind_clause = "kind = 'file'" if decomposition.files_only else "kind IN ('file', 'directory')"

        # SELECT only what the entries need — content is excluded from the
        # default glob projection so we don't ship every file's body for
        # a path-pattern listing.
        select_cols = ", ".join(sorted(cols))
        sql = text(f"""
            SELECT {top_clause}{select_cols}
            FROM {table}
            WHERE {kind_clause}
              AND deleted_at IS NULL
              {like_clause}
              {regex_clause}
              {filter_clause}
            ORDER BY path
        """)

        rows = (await session.execute(sql, params)).all()
        matched = [self._row_to_entry(row, cols) for row in rows]
        return self._unscope_result(VFSResult(function="glob", entries=matched), user_id)
