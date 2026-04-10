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

from grover.backends.database import DatabaseFileSystem
from grover.bm25 import tokenize_query
from grover.paths import scope_path
from grover.patterns import compile_glob, glob_to_sql_like
from grover.results import Candidate, Detail, GroverResult

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


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
    the ``GroverObject`` table and a full-text index on its ``content``
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
        on ``GroverFileSystem`` at init time) so raw queries resolve to
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

        1. The ``GroverObject`` table is resolvable in the connection's
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
                    f"  CREATE FULLTEXT CATALOG grover_ftcat;\n"
                    f"  CREATE UNIQUE NONCLUSTERED INDEX ux_{bare_table}_id "
                    f"ON {table}(id);\n"
                    f"  CREATE FULLTEXT INDEX ON {table}(content LANGUAGE 1033)\n"
                    f"  KEY INDEX ux_{bare_table}_id\n"
                    f"  ON grover_ftcat WITH CHANGE_TRACKING AUTO;"
                )

    # ------------------------------------------------------------------
    # Lexical search — CONTAINSTABLE pushdown (files only)
    # ------------------------------------------------------------------

    async def _lexical_search_impl(
        self,
        query: str,
        k: int = 15,
        candidates: GroverResult | None = None,
        *,
        user_id: str | None = None,
        session: AsyncSession,
    ) -> GroverResult:
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

        When *candidates* is passed, the path list is intersected via
        ``o.path IN (…)``.  If the candidate set exceeds the dialect
        parameter budget (2000 binds on MSSQL), the query is chunked
        via the inherited ``_chunk_paths`` and the per-chunk results
        are merged before the final top-*k* cut.
        """
        self._require_user_id(user_id)
        candidates = self._scope_candidates(candidates, user_id)
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

        if candidates is None:
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
            result = GroverResult(
                candidates=[
                    Candidate(
                        path=row.path,
                        kind=row.kind,
                        details=(Detail(operation="lexical_search", score=float(row.score)),),
                    )
                    for row in rows
                ]
            )
            return self._unscope_result(result, user_id)

        # Candidates path: intersect via IN-list, chunk if needed.
        candidate_paths = [c.path for c in candidates.candidates]
        if not candidate_paths:
            return self._unscope_result(GroverResult(candidates=[]), user_id)

        merged: dict[str, tuple[str | None, float]] = {}
        for batch in self._chunk_paths(session, candidate_paths, binds_per_item=1):
            in_clause = ", ".join(f":p{i}" for i in range(len(batch)))
            sql = text(f"""
                SELECT TOP (:k) o.path, o.kind, ct.[RANK] AS score
                FROM CONTAINSTABLE({table}, content, :expr, :top_n) AS ct
                INNER JOIN {table} AS o ON o.id = ct.[KEY]
                WHERE o.kind = 'file'
                  AND o.deleted_at IS NULL
                  AND o.path IN ({in_clause})
                  {user_scope_clause}
                ORDER BY ct.[RANK] DESC
            """)
            params = {**params_base, "k": k}
            for i, p in enumerate(batch):
                params[f"p{i}"] = p
            rows = (await session.execute(sql, params)).all()
            for row in rows:
                # Keep the highest-ranked occurrence per path
                prev = merged.get(row.path)
                score = float(row.score)
                if prev is None or score > prev[1]:
                    merged[row.path] = (row.kind, score)

        ordered = sorted(merged.items(), key=lambda kv: kv[1][1], reverse=True)[:k]
        result = GroverResult(
            candidates=[
                Candidate(
                    path=path,
                    kind=kind,
                    details=(Detail(operation="lexical_search", score=score),),
                )
                for path, (kind, score) in ordered
            ]
        )
        return self._unscope_result(result, user_id)

    # ------------------------------------------------------------------
    # Grep — REGEXP_LIKE pushdown with optional CONTAINS pre-filter
    # ------------------------------------------------------------------

    async def _grep_impl(
        self,
        pattern: str,
        case_sensitive: bool = True,
        max_results: int | None = None,
        candidates: GroverResult | None = None,
        *,
        user_id: str | None = None,
        session: AsyncSession,
    ) -> GroverResult:
        """Regex content search pushed into SQL via ``REGEXP_LIKE``.

        Operates on files only; chunks and versions are excluded.

        Two pushdown paths:

        1. **Literal pre-filter** (preferred when extractable): build a
           Full-Text ``CONTAINS`` expression from literal alphanumeric
           runs in the regex (via :func:`_extract_literal_terms`),
           ``JOIN`` ``CONTAINSTABLE`` to the table, then add
           ``REGEXP_LIKE`` to the WHERE so only the narrow candidate set
           is regex-scanned.

        2. **Direct REGEXP_LIKE**: when no literals can be safely
           extracted (pure character-class / alternation patterns),
           run ``REGEXP_LIKE`` against the table with ``MAXDOP 1``
           (matches the configuration that gave Brent Ozar 1.86M
           rows/sec post-RTM).

        Per-line metadata is built client-side via the inherited
        :meth:`_collect_line_matches` helper, but only on the already-
        narrow result set — content for matched files is fetched in the
        same query.

        ``REGEXP_LIKE`` has a 2 MB LOB ceiling — only the first ~1M
        characters of an ``nvarchar(max)`` value are scanned.  For
        typical source code and docs this never matters.
        """
        self._require_user_id(user_id)
        candidates = self._scope_candidates(candidates, user_id)
        if not pattern:
            return self._error("grep requires a pattern")

        flags = 0 if case_sensitive else re.IGNORECASE
        try:
            regex = re.compile(pattern, flags)
        except re.error as exc:
            return self._error(f"Invalid regex pattern: {exc}")

        # Always include 'm' (multi-line) so ^ and $ match at line
        # boundaries — this matches the base class's per-line Python
        # grep and grep(1) conventions.  Without 'm', SQL Server's
        # REGEXP_LIKE treats ^/$ as start/end-of-string only.
        sql_flags = "cm" if case_sensitive else "im"
        table = self._resolve_table()
        params: dict[str, object] = {"pattern": pattern, "flags": sql_flags}

        user_scope_clause = ""
        if self._user_scoped and user_id:
            user_scope_clause = " AND o.path LIKE :user_scope ESCAPE '\\'"
            params["user_scope"] = f"/{user_id}/%"

        if candidates is not None:
            candidate_paths = [c.path for c in candidates.candidates if c.kind in (None, "file")]
            if not candidate_paths:
                return self._unscope_result(GroverResult(candidates=[]), user_id)
            content_map = await self._grep_with_candidate_chunks(
                session=session,
                regex_pattern=pattern,
                sql_flags=sql_flags,
                user_scope_clause=user_scope_clause,
                user_scope_value=params.get("user_scope"),
                candidate_paths=candidate_paths,
                max_results=max_results,
            )
        else:
            literal_terms = _extract_literal_terms(pattern)
            top_clause = ""
            if max_results is not None:
                top_clause = "TOP (:max_results) "
                params["max_results"] = max_results

            if literal_terms:
                contains_expr = " AND ".join(_quote_contains_term(t) for t in literal_terms)
                params["expr"] = contains_expr
                sql = text(f"""
                    SELECT {top_clause}o.path, o.content
                    FROM CONTAINSTABLE({table}, content, :expr) AS ct
                    INNER JOIN {table} AS o ON o.id = ct.[KEY]
                    WHERE o.kind = 'file'
                      AND o.deleted_at IS NULL
                      AND o.content IS NOT NULL
                      AND REGEXP_LIKE(o.content, :pattern, CAST(:flags AS VARCHAR(4)))
                      {user_scope_clause}
                    ORDER BY o.path
                """)
            else:
                sql = text(f"""
                    SELECT {top_clause}o.path, o.content
                    FROM {table} AS o
                    WHERE o.kind = 'file'
                      AND o.deleted_at IS NULL
                      AND o.content IS NOT NULL
                      AND REGEXP_LIKE(o.content, :pattern, CAST(:flags AS VARCHAR(4)))
                      {user_scope_clause}
                    ORDER BY o.path
                    OPTION (MAXDOP 1)
                """)

            rows = (await session.execute(sql, params)).all()
            content_map = {row.path: row.content for row in rows if row.content}

        matched = self._collect_line_matches(content_map, regex, max_results)
        return self._unscope_result(GroverResult(candidates=matched), user_id)

    async def _grep_with_candidate_chunks(
        self,
        *,
        session: AsyncSession,
        regex_pattern: str,
        sql_flags: str,
        user_scope_clause: str,
        user_scope_value: object | None,
        candidate_paths: list[str],
        max_results: int | None,
    ) -> dict[str, str]:
        """Run ``REGEXP_LIKE`` per chunk for an explicit candidate path list.

        Splits *candidate_paths* into batches respecting the dialect
        parameter budget and runs the regex pushdown on each.  Returns
        a ``{path: content}`` map for the matched rows.  No CONTAINS
        pre-filter — the candidate list is already narrow.
        """
        table = self._resolve_table()
        content_map: dict[str, str] = {}
        for batch in self._chunk_paths(session, candidate_paths, binds_per_item=1):
            in_clause = ", ".join(f":p{i}" for i in range(len(batch)))
            params: dict[str, object] = {"pattern": regex_pattern, "flags": sql_flags}
            for i, p in enumerate(batch):
                params[f"p{i}"] = p
            if user_scope_value is not None:
                params["user_scope"] = user_scope_value
            sql = text(f"""
                SELECT o.path, o.content
                FROM {table} AS o
                WHERE o.kind = 'file'
                  AND o.deleted_at IS NULL
                  AND o.content IS NOT NULL
                  AND o.path IN ({in_clause})
                  AND REGEXP_LIKE(o.content, :pattern, CAST(:flags AS VARCHAR(4)))
                  {user_scope_clause}
                ORDER BY o.path
            """)
            rows = (await session.execute(sql, params)).all()
            for row in rows:
                if row.content:
                    content_map[row.path] = row.content
            if max_results is not None and len(content_map) >= max_results:
                break
        return content_map

    # ------------------------------------------------------------------
    # Glob — REGEXP_LIKE pushdown on path
    # ------------------------------------------------------------------

    async def _glob_impl(
        self,
        pattern: str,
        candidates: GroverResult | None = None,
        *,
        user_id: str | None = None,
        session: AsyncSession,
    ) -> GroverResult:
        """Glob match with the authoritative regex pushed into SQL.

        The base class already pushes ``LIKE`` to SQL, but then re-checks
        every returned row in Python with ``compile_glob(pattern).match``.
        That's a network round-trip and a Python loop for every row that
        ``LIKE`` over-matched (e.g. ``**/test_*.py`` LIKEs to
        ``%test_%.py``, which over-matches ``foo_test_bar.py``).

        This override keeps the SARGable ``LIKE`` pre-filter (so a
        leading literal prefix can still drive an index seek) and adds
        ``REGEXP_LIKE(path, :glob_regex, 'c')`` as the authoritative
        gate, eliminating the Python post-filter and moving the sort
        into SQL via ``ORDER BY path``.

        ``compile_glob`` produces plain POSIX-style regexes from
        ``fnmatch.translate``-equivalent rules — no Python-only syntax
        — so the regex source string can be passed directly to
        ``REGEXP_LIKE``.  The 2 MB LOB ceiling does not apply to the
        ``path`` column.
        """
        self._require_user_id(user_id)
        candidates = self._scope_candidates(candidates, user_id)
        if candidates is None and self._user_scoped and user_id:
            pattern = scope_path(pattern, user_id) if pattern.startswith("/") else f"/{user_id}/{pattern}"
        if not pattern:
            return self._error("glob requires a pattern")

        regex = compile_glob(pattern)
        if regex is None:
            return self._error(f"Invalid glob pattern: {pattern}")

        # In-memory candidate path: identical to base class.
        if candidates is not None:
            matched = [
                Candidate(path=c.path, kind=c.kind, details=(Detail(operation="glob"),))
                for c in candidates.candidates
                if regex.match(c.path) is not None
            ]
            return self._unscope_result(GroverResult(candidates=matched), user_id)

        table = self._resolve_table()
        like_pattern = glob_to_sql_like(pattern)
        like_clause = "AND path LIKE :like_pattern ESCAPE '\\'" if like_pattern is not None else ""

        sql = text(f"""
            SELECT path, kind
            FROM {table}
            WHERE kind IN ('file', 'directory')
              AND deleted_at IS NULL
              {like_clause}
              AND REGEXP_LIKE(path, :glob_regex, 'c')
            ORDER BY path
        """)
        params: dict[str, object] = {"glob_regex": regex.pattern}
        if like_pattern is not None:
            params["like_pattern"] = like_pattern

        rows = (await session.execute(sql, params)).all()
        matched = [Candidate(path=row.path, kind=row.kind, details=(Detail(operation="glob"),)) for row in rows]
        return self._unscope_result(GroverResult(candidates=matched), user_id)
