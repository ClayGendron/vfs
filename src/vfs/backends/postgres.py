"""PostgresFileSystem — PostgreSQL backend with native FTS, regex, and pgvector.

Subclass of :class:`vfs.backends.database.DatabaseFileSystem` that keeps the
public VFS contract unchanged while pushing search work into PostgreSQL.

Schema responsibility: this class does **not** create extensions, indexes, or
generated columns during request handling. Call
:meth:`verify_native_search_schema` at startup to fail fast on a misconfigured
database.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any, ClassVar, cast

from sqlalchemy import Text, bindparam, text
from sqlalchemy.dialects.postgresql import ARRAY

from vfs.backends.database import (
    DatabaseFileSystem,
    _compile_grep_regex,
    _escape_like,
    _extract_literal_terms,
    _regex_flags_for_mode,
)
from vfs.bm25 import tokenize_query
from vfs.models import postgres_vector_column_spec, resolve_embedding_vector_type
from vfs.paths import scope_path
from vfs.patterns import compile_glob, decompose_glob, glob_to_sql_like
from vfs.results import Entry, VFSResult

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from vfs.query.ast import CaseMode, GrepOutputMode


def _quote_tsquery_term(term: str) -> str:
    """Return a tsquery-safe lexeme literal."""
    return "'" + term.replace("\\", "\\\\").replace("'", "''") + "'"


def _build_tsquery(terms: list[str] | tuple[str, ...], *, operator: str) -> str:
    """Join tokenized terms into a Postgres tsquery string."""
    return f" {operator} ".join(_quote_tsquery_term(term) for term in terms)


def _build_plainto_tsquery(terms: list[str] | tuple[str, ...], *, config: str) -> tuple[str, dict[str, str]]:
    """Return a parameterized OR tsquery expression built from bound terms."""
    if not terms:
        msg = "terms must not be empty"
        raise ValueError(msg)

    fragments: list[str] = []
    params: dict[str, str] = {}
    for idx, term in enumerate(terms):
        param_name = f"t{idx}"
        fragments.append(f"plainto_tsquery('{config}', :{param_name})")
        params[param_name] = term
    return " || ".join(fragments), params


def _python_regex_to_postgres(pattern: str) -> str:
    """Translate the small regex subset we synthesize into Postgres ARE syntax.

    Walks the pattern respecting escape pairs and character-class context so
    that ``\\b``/``\\A``/``\\Z`` inside an escaped-backslash run or ``(?:`` inside
    ``[...]`` are not mangled — both shapes are silent false-negative sources
    for the grep pre-filter if translated naively.
    """
    out: list[str] = []
    i = 0
    length = len(pattern)
    in_class = False
    while i < length:
        ch = pattern[i]
        if ch == "\\" and i + 1 < length:
            nxt = pattern[i + 1]
            if not in_class and nxt == "b":
                out.append(r"\y")
            elif not in_class and nxt == "A":
                out.append("^")
            elif not in_class and nxt == "Z":
                out.append("$")
            else:
                out.append(ch + nxt)
            i += 2
            continue
        if in_class:
            if ch == "]":
                in_class = False
            out.append(ch)
            i += 1
            continue
        if ch == "[":
            in_class = True
            out.append(ch)
            i += 1
            continue
        if pattern.startswith("(?:", i):
            out.append("(")
            i += 3
            continue
        out.append(ch)
        i += 1
    return "".join(out)


def _parse_vector_dimension(formatted_type: str | None) -> int | None:
    """Extract ``N`` from ``vector(N)``."""
    if formatted_type is None:
        return None
    match = re.fullmatch(r"vector\((\d+)\)", formatted_type.strip())
    if match is None:
        return None
    return int(match.group(1))


def _contains_unescaped_anchor(pattern: str) -> bool:
    """Return whether *pattern* contains a line/stream anchor token.

    Grep's authoritative matcher runs line-by-line in Python. A whole-file
    Postgres regex predicate is only a sound pre-filter when any line hit
    also implies a whole-content hit. ``^``, ``$``, ``\\A``, and ``\\Z`` break
    that implication for non-first/non-last lines, so anchored patterns skip
    regex pushdown and rely on structural/literal narrowing only.
    """
    in_class = False
    i = 0
    while i < len(pattern):
        ch = pattern[i]
        if ch == "\\" and i + 1 < len(pattern):
            nxt = pattern[i + 1]
            if not in_class and nxt in {"A", "Z"}:
                return True
            i += 2
            continue
        if in_class:
            if ch == "]":
                in_class = False
            i += 1
            continue
        if ch == "[":
            in_class = True
            i += 1
            continue
        if ch in {"^", "$"}:
            return True
        i += 1
    return False


def _pgvector_distance_operator(operator_class: str) -> str:
    """Return the pgvector SQL operator for a declared operator class."""
    if operator_class == "vector_cosine_ops":
        return "<=>"
    if operator_class == "vector_ip_ops":
        return "<#>"
    if operator_class == "vector_l2_ops":
        return "<->"
    msg = (
        "PostgresFileSystem only supports pgvector operator classes "
        f"'vector_cosine_ops', 'vector_ip_ops', and 'vector_l2_ops'; got {operator_class!r}"
    )
    raise RuntimeError(msg)


def _pgvector_distance_to_score(operator_class: str, distance: float) -> float:
    """Translate a pgvector distance/order key into Entry.score semantics."""
    if operator_class == "vector_cosine_ops":
        return 1.0 - distance
    if operator_class == "vector_ip_ops":
        # ``<#>`` returns negative inner product so ASC ordering still works.
        return -distance
    if operator_class == "vector_l2_ops":
        # Convert non-negative Euclidean distance into a bounded similarity.
        return 1.0 / (1.0 + distance)
    msg = (
        "PostgresFileSystem only supports pgvector operator classes "
        f"'vector_cosine_ops', 'vector_ip_ops', and 'vector_l2_ops'; got {operator_class!r}"
    )
    raise RuntimeError(msg)


class PostgresFileSystem(DatabaseFileSystem):
    """PostgreSQL-native backend with FTS, regex pushdown, and pgvector."""

    FULLTEXT_CONFIG: ClassVar[str] = "simple"
    VECTOR_INDEX_METHODS: ClassVar[tuple[str, ...]] = ("hnsw", "ivfflat")

    def _pattern_schema_hint(self) -> str:
        """Return the required pg_trgm/path-index DDL contract."""
        table = self._resolve_table()
        bare_table = str(self._model.__tablename__)
        return (
            "Provision the native Postgres pattern-search artifacts outside the application, for example:\n"
            "  CREATE EXTENSION IF NOT EXISTS pg_trgm;\n"
            f"  CREATE INDEX ix_{bare_table}_path_pattern\n"
            f"  ON {table} (path text_pattern_ops)\n"
            "  WHERE deleted_at IS NULL;\n"
            f"  CREATE INDEX ix_{bare_table}_path_trgm_gin\n"
            f"  ON {table} USING GIN (path gin_trgm_ops)\n"
            "  WHERE deleted_at IS NULL;\n"
            f"  CREATE INDEX ix_{bare_table}_content_trgm_gin\n"
            f"  ON {table} USING GIN (content gin_trgm_ops)\n"
            "  WHERE kind = 'file'\n"
            "    AND content IS NOT NULL\n"
            "    AND deleted_at IS NULL;"
        )

    def _fulltext_schema_hint(self) -> str:
        """Return the required native FTS DDL contract for this backend."""
        table = self._resolve_table()
        bare_table = str(self._model.__tablename__)
        return (
            "Provision the native FTS artifacts outside the application, for example:\n"
            f"  ALTER TABLE {table}\n"
            "  ADD COLUMN search_tsv tsvector GENERATED ALWAYS AS (\n"
            f"      to_tsvector('{self.FULLTEXT_CONFIG}', coalesce(content, ''))\n"
            "  ) STORED;\n"
            f"  CREATE INDEX ix_{bare_table}_search_tsv_gin\n"
            f"  ON {table} USING GIN (search_tsv)\n"
            "  WHERE content IS NOT NULL\n"
            "    AND deleted_at IS NULL\n"
            "    AND kind != 'version';"
        )

    @staticmethod
    def _normalize_catalog_sql(value: str | None) -> str:
        """Canonicalize catalog SQL snippets for tolerant substring/regex checks."""
        if not value:
            return ""
        normalized = " ".join(value.lower().split())
        return normalized.replace("!=", "<>")

    @classmethod
    def _has_live_search_predicate(cls, predicate: str | None) -> bool:
        """Return whether *predicate* matches the live search partial-index contract."""
        normalized = cls._normalize_catalog_sql(predicate)
        if not normalized:
            return False
        return (
            "content is not null" in normalized
            and "deleted_at is null" in normalized
            and "kind" in normalized
            and "'version'" in normalized
            and "<>" in normalized
        )

    @classmethod
    def _has_live_path_predicate(cls, predicate: str | None) -> bool:
        normalized = cls._normalize_catalog_sql(predicate)
        return bool(normalized) and "deleted_at is null" in normalized

    @classmethod
    def _has_live_file_content_predicate(cls, predicate: str | None) -> bool:
        normalized = cls._normalize_catalog_sql(predicate)
        return (
            bool(normalized)
            and "content is not null" in normalized
            and "deleted_at is null" in normalized
            and "kind" in normalized
            and "'file'" in normalized
        )

    def _resolve_table(self) -> str:
        """Return the schema-qualified table name for raw ``text()`` SQL."""
        table = str(self._model.__tablename__)
        return f"{self._schema}.{table}" if self._schema else table

    async def verify_native_search_schema(self) -> None:
        """Confirm the database has the native artifacts required by this backend."""
        async with self._use_session() as session:
            await self._verify_fulltext_schema(session)
            await self._verify_pattern_schema(session)
            if self._vector_store is None:
                await self._verify_vector_schema(session)

    async def _verify_pattern_schema(self, session: AsyncSession) -> None:
        if getattr(self, "_native_pattern_verified", False):
            return

        table = self._resolve_table()
        object_id = (await session.execute(text("SELECT to_regclass(:table)::oid"), {"table": table})).scalar()
        if object_id is None:
            raise RuntimeError(
                f"PostgresFileSystem requires table '{table}' to exist. Run "
                f"SQLModel.metadata.create_all first or grant access to the existing table."
            )

        extension_exists = (
            await session.execute(
                text("SELECT 1 FROM pg_extension WHERE extname = 'pg_trgm'"),
            )
        ).scalar()
        if extension_exists is None:
            raise RuntimeError(
                "PostgresFileSystem requires the pg_trgm extension for native pattern search. "
                "Provision it outside the application with:\n"
                "  CREATE EXTENSION IF NOT EXISTS pg_trgm;"
            )

        index_rows = (
            await session.execute(
                text("""
                    SELECT
                        idx.relname AS index_name,
                        pg_get_indexdef(i.indexrelid) AS indexdef,
                        pg_get_expr(i.indpred, i.indrelid) AS predicate
                    FROM pg_index AS i
                    JOIN pg_class AS idx ON idx.oid = i.indexrelid
                    WHERE i.indrelid = :oid
                """),
                {"oid": object_id},
            )
        ).all()

        normalized_defs = [
            (row.index_name, self._normalize_catalog_sql(row.indexdef), row.predicate) for row in index_rows
        ]

        path_pattern_indexes = [
            (name, predicate)
            for name, indexdef, predicate in normalized_defs
            if re.search(r"using\s+btree\s*\(\s*path\s+text_pattern_ops\s*\)", indexdef) is not None
        ]
        if not any(self._has_live_path_predicate(predicate) for _, predicate in path_pattern_indexes):
            raise RuntimeError(
                f"PostgresFileSystem requires a partial B-tree text_pattern_ops index on '{table}.path' "
                "with predicate `deleted_at IS NULL`. "
                f"{self._pattern_schema_hint()}"
            )

        path_trgm_indexes = [
            (name, predicate)
            for name, indexdef, predicate in normalized_defs
            if re.search(r"using\s+gin\s*\(\s*path\s+gin_trgm_ops\s*\)", indexdef) is not None
        ]
        if not any(self._has_live_path_predicate(predicate) for _, predicate in path_trgm_indexes):
            raise RuntimeError(
                f"PostgresFileSystem requires a partial trigram GIN index on '{table}.path' "
                "with predicate `deleted_at IS NULL`. "
                f"{self._pattern_schema_hint()}"
            )

        content_trgm_indexes = [
            (name, predicate)
            for name, indexdef, predicate in normalized_defs
            if re.search(r"using\s+gin\s*\(\s*content\s+gin_trgm_ops\s*\)", indexdef) is not None
        ]
        if not any(self._has_live_file_content_predicate(predicate) for _, predicate in content_trgm_indexes):
            raise RuntimeError(
                f"PostgresFileSystem requires a partial trigram GIN index on '{table}.content' "
                "with predicate `kind = 'file' AND content IS NOT NULL AND deleted_at IS NULL`. "
                f"{self._pattern_schema_hint()}"
            )

        self._native_pattern_verified = True

    async def _verify_fulltext_schema(self, session: AsyncSession) -> None:
        if getattr(self, "_native_fulltext_verified", False):
            return

        table = self._resolve_table()
        object_id = (await session.execute(text("SELECT to_regclass(:table)::oid"), {"table": table})).scalar()
        if object_id is None:
            raise RuntimeError(
                f"PostgresFileSystem requires table '{table}' to exist. Run "
                f"SQLModel.metadata.create_all first or grant access to the existing table."
            )

        content_column_exists = (
            await session.execute(
                text("SELECT 1 FROM pg_attribute WHERE attrelid = :oid AND attname = 'content' AND NOT attisdropped"),
                {"oid": object_id},
            )
        ).scalar()
        if content_column_exists is None:
            raise RuntimeError(f"PostgresFileSystem requires a 'content' column on '{table}'.")

        search_tsv_row = (
            await session.execute(
                text("""
                    SELECT
                        format_type(att.atttypid, att.atttypmod) AS formatted_type,
                        att.attgenerated,
                        pg_get_expr(def.adbin, def.adrelid) AS generation_expr
                    FROM pg_attribute AS att
                    LEFT JOIN pg_attrdef AS def
                      ON def.adrelid = att.attrelid AND def.adnum = att.attnum
                    WHERE att.attrelid = :oid
                      AND att.attname = 'search_tsv'
                      AND NOT att.attisdropped
                """),
                {"oid": object_id},
            )
        ).first()
        if search_tsv_row is None:
            raise RuntimeError(
                f"PostgresFileSystem requires a stored generated 'search_tsv' column on '{table}'. "
                f"{self._fulltext_schema_hint()}"
            )

        formatted_type, generated_flag, generation_expr = search_tsv_row
        if formatted_type != "tsvector":
            raise RuntimeError(
                f"PostgresFileSystem requires '{table}.search_tsv' to be tsvector; found {formatted_type!r}. "
                f"{self._fulltext_schema_hint()}"
            )
        if generated_flag != "s" and not generation_expr:
            raise RuntimeError(
                f"PostgresFileSystem requires '{table}.search_tsv' to be GENERATED ALWAYS ... STORED. "
                f"{self._fulltext_schema_hint()}"
            )

        normalized_expr = self._normalize_catalog_sql(generation_expr)
        if (
            "to_tsvector" not in normalized_expr
            or "content" not in normalized_expr
            or self.FULLTEXT_CONFIG.lower() not in normalized_expr
        ):
            raise RuntimeError(
                f"PostgresFileSystem requires '{table}.search_tsv' to be generated from "
                f"to_tsvector('{self.FULLTEXT_CONFIG}', coalesce(content, '')). "
                f"{self._fulltext_schema_hint()}"
            )

        index_rows = (
            await session.execute(
                text("""
                    SELECT
                        idx.relname AS index_name,
                        pg_get_indexdef(i.indexrelid) AS indexdef,
                        pg_get_expr(i.indpred, i.indrelid) AS predicate
                    FROM pg_index AS i
                    JOIN pg_class AS idx ON idx.oid = i.indexrelid
                    JOIN pg_am AS am ON am.oid = idx.relam
                    WHERE i.indrelid = :oid
                      AND am.amname = 'gin'
                """),
                {"oid": object_id},
            )
        ).all()

        search_tsv_indexes = [
            row
            for row in index_rows
            if re.search(
                r"using\s+gin\s*\(\s*search_tsv\s*\)",
                self._normalize_catalog_sql(row.indexdef),
            )
            is not None
        ]
        if not search_tsv_indexes:
            raise RuntimeError(
                f"PostgresFileSystem requires a GIN index on '{table}.search_tsv'. {self._fulltext_schema_hint()}"
            )

        if not any(self._has_live_search_predicate(row.predicate) for row in search_tsv_indexes):
            raise RuntimeError(
                f"PostgresFileSystem requires at least one partial GIN index on '{table}.search_tsv' with the "
                "live-search predicate `content IS NOT NULL AND deleted_at IS NULL AND kind != 'version'`. "
                f"{self._fulltext_schema_hint()}"
            )

        self._native_fulltext_verified = True

    async def _verify_vector_schema(self, session: AsyncSession) -> None:
        if getattr(self, "_native_vector_verified", False):
            return

        table = self._resolve_table()
        bare_table = str(self._model.__tablename__)
        try:
            vector_spec = postgres_vector_column_spec(self._model)
        except ValueError as exc:
            raise RuntimeError(str(exc)) from exc

        object_id = (await session.execute(text("SELECT to_regclass(:table)::oid"), {"table": table})).scalar()
        if object_id is None:
            raise RuntimeError(
                f"PostgresFileSystem requires table '{table}' to exist before native vector search can run."
            )

        extension_exists = (
            await session.execute(
                text("SELECT 1 FROM pg_extension WHERE extname = 'vector'"),
            )
        ).scalar()
        if extension_exists is None:
            raise RuntimeError(
                "PostgresFileSystem requires the pgvector extension. Provision it outside the application with:\n"
                "  CREATE EXTENSION IF NOT EXISTS vector;"
            )

        type_row = (
            await session.execute(
                text("""
                    SELECT format_type(atttypid, atttypmod)
                    FROM pg_attribute
                    WHERE attrelid = :oid AND attname = :column AND NOT attisdropped
                """),
                {"oid": object_id, "column": vector_spec.column_name},
            )
        ).first()
        if type_row is None:
            raise RuntimeError(
                f"PostgresFileSystem requires a native vector column at '{table}.{vector_spec.column_name}'."
            )

        formatted_type = type_row[0]
        live_dimension = _parse_vector_dimension(formatted_type)
        if live_dimension is None:
            raise RuntimeError(
                f"PostgresFileSystem found a non-native embedding column at "
                f"'{table}.{vector_spec.column_name}': expected vector({vector_spec.dimension}), "
                f"found {formatted_type!r}. "
                f"Run the explicit migration path for legacy serialized embeddings before using native pgvector on "
                f"'{bare_table}'."
            )
        if live_dimension != vector_spec.dimension:
            raise RuntimeError(
                f"PostgresFileSystem model/database dimension mismatch for '{table}.{vector_spec.column_name}': "
                f"model declares vector({vector_spec.dimension}) but the database column is vector({live_dimension})."
            )

        vector_index_exists = (
            await session.execute(
                text("""
                    SELECT 1
                    FROM pg_index AS i
                    JOIN pg_class AS idx ON idx.oid = i.indexrelid
                    JOIN pg_am AS am ON am.oid = idx.relam
                    JOIN pg_attribute AS att ON att.attrelid = i.indrelid AND att.attnum = ANY(i.indkey)
                    JOIN pg_opclass AS opc ON opc.oid = ANY(i.indclass)
                    WHERE i.indrelid = :oid
                      AND att.attname = :column
                      AND am.amname = ANY(:methods)
                      AND opc.opcname = :opclass
                    LIMIT 1
                """).bindparams(
                    bindparam("methods", type_=cast("Any", ARRAY(Text()))),
                ),
                {
                    "oid": object_id,
                    "column": vector_spec.column_name,
                    "methods": list(self.VECTOR_INDEX_METHODS),
                    "opclass": vector_spec.operator_class,
                },
            )
        ).scalar()
        if vector_index_exists is None:
            raise RuntimeError(
                f"PostgresFileSystem requires an ANN index on '{table}.{vector_spec.column_name}' "
                f"using {vector_spec.operator_class}. Provision one outside the application, for example:\n"
                f"  CREATE INDEX {vector_spec.index_name}\n"
                f"  ON {table} USING {vector_spec.index_method} "
                f"({vector_spec.column_name} {vector_spec.operator_class})\n"
                f"  WHERE {vector_spec.column_name} IS NOT NULL;"
            )

        self._native_vector_verified = True

    def _structural_regex_clause(self, col: str, param_name: str, regex_pattern: str) -> tuple[str, str]:
        return f"{col} ~ {param_name}", _python_regex_to_postgres(regex_pattern)

    async def _lexical_search_impl(
        self,
        query: str,
        k: int = 15,
        candidates: VFSResult | None = None,
        *,
        user_id: str | None = None,
        session: AsyncSession,
    ) -> VFSResult:
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

        table = self._resolve_table()
        unique_terms = list(dict.fromkeys(terms))
        tsquery_sql, tsquery_params = _build_plainto_tsquery(unique_terms, config=self.FULLTEXT_CONFIG)
        params: dict[str, object] = {"k": k, **tsquery_params}
        user_scope_clause = ""
        if self._user_scoped and user_id:
            user_scope_clause = "AND o.path LIKE :user_scope ESCAPE '\\'"
            params["user_scope"] = f"/{user_id}/%"

        ranking_sql = text(f"""
            WITH query AS (
                SELECT {tsquery_sql} AS q
            )
            SELECT
                o.path,
                o.kind,
                o.content,
                ts_rank_cd(o.search_tsv, query.q, 1|32) AS score
            FROM {table} AS o
            CROSS JOIN query
            WHERE o.kind != 'version'
              AND o.deleted_at IS NULL
              AND o.content IS NOT NULL
              AND o.search_tsv @@ query.q
              {user_scope_clause}
            ORDER BY score DESC, o.path
            LIMIT :k
        """)
        rows = (await session.execute(ranking_sql, params)).all()
        if not rows:
            return VFSResult(function="lexical_search", entries=[])

        result = VFSResult(
            function="lexical_search",
            entries=[
                Entry(
                    path=row.path,
                    kind=row.kind,
                    content=row.content,
                    score=float(row.score),
                )
                for row in rows
            ],
        )
        return self._unscope_result(result, user_id)

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

        await self._verify_pattern_schema(session)
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

        table = self._resolve_table()
        filter_clause, filter_params = self._build_structural_sql(
            ext=ext,
            ext_not=ext_not,
            paths=paths,
            globs=globs,
            globs_not=globs_not,
            user_id=user_id,
            alias="o",
        )

        files_only = output_mode == "files" and not invert_match
        select_set = cols | {"content"}
        select_cols = ", ".join(f"o.{column}" for column in sorted(select_set))

        params: dict[str, object] = dict(filter_params)
        regex_clause = ""
        literal_clauses: list[str] = []
        if not invert_match:
            case_insensitive = bool(_regex_flags_for_mode(case_mode, pattern) & re.IGNORECASE)
            if fixed_strings:
                operator = "ILIKE" if case_insensitive else "LIKE"
                params["fixed_like"] = "%" + _escape_like(pattern) + "%"
                literal_clauses.append(f"o.content {operator} :fixed_like ESCAPE '\\'")
            literal_terms = _extract_literal_terms(regex.pattern)
            operator = "ILIKE" if case_insensitive else "LIKE"
            for idx, term in enumerate(literal_terms):
                key = f"literal_like_{idx}"
                params[key] = "%" + _escape_like(term) + "%"
                literal_clauses.append(f"o.content {operator} :{key} ESCAPE '\\'")
            if not _contains_unescaped_anchor(regex.pattern):
                regex_operator = "~*" if case_insensitive else "~"
                params["pattern"] = _python_regex_to_postgres(regex.pattern)
                regex_clause = f"AND o.content {regex_operator} :pattern"

        sql = text(f"""
            SELECT {select_cols}
            FROM {table} AS o
            WHERE o.kind = 'file'
              AND o.deleted_at IS NULL
              AND o.content IS NOT NULL
              {"AND " + " AND ".join(literal_clauses) if literal_clauses else ""}
              {regex_clause}
              {filter_clause}
            ORDER BY o.path
        """)
        rows = (await session.execute(sql, params)).all()

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
        if files_only:
            matched = [Entry(path=entry.path, kind="file") for entry in matched]
        return self._unscope_result(VFSResult(function="grep", entries=matched), user_id)

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

        await self._verify_pattern_schema(session)
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

        decomposition = decompose_glob(unscoped_pattern)
        if ext and decomposition.ext:
            merged_ext = tuple(value for value in ext if value in decomposition.ext)
            if not merged_ext:
                return self._unscope_result(VFSResult(function="glob", entries=[]), user_id)
        elif decomposition.ext:
            merged_ext = decomposition.ext
        else:
            merged_ext = ext

        merged_paths = paths or ()

        table = self._resolve_table()
        filter_clause, filter_params = self._build_structural_sql(
            ext=merged_ext,
            ext_not=(),
            paths=merged_paths,
            globs=(),
            globs_not=(),
            user_id=user_id,
            alias="",
        )
        prefix_clause = ""
        prefix_params: dict[str, object] = {}
        if decomposition.prefix is not None:
            prefix_clause, prefix_params = self._build_structural_sql(
                ext=(),
                ext_not=(),
                paths=(decomposition.prefix,),
                globs=(),
                globs_not=(),
                user_id=user_id,
                alias="",
            )

        params: dict[str, object] = dict(filter_params)
        params.update(prefix_params)
        like_clause = ""
        like_pattern = glob_to_sql_like(pattern)
        if like_pattern is not None:
            like_clause = "AND path LIKE :like_pattern ESCAPE '\\'"
            params["like_pattern"] = like_pattern

        params["glob_regex"] = _python_regex_to_postgres(regex.pattern)
        regex_clause = "AND path ~ :glob_regex"
        kind_clause = "kind = 'file'" if decomposition.files_only else "kind IN ('file', 'directory')"

        select_cols = ", ".join(sorted(cols))
        sql = text(f"""
            SELECT {select_cols}
            FROM {table}
            WHERE {kind_clause}
              AND deleted_at IS NULL
              {like_clause}
              {regex_clause}
              {prefix_clause}
              {filter_clause}
            ORDER BY path
        """)
        rows = (await session.execute(sql, params)).all()
        matched: list[Entry] = []
        for row in rows:
            if regex.match(row.path) is None:
                continue
            matched.append(self._row_to_entry(row, cols))
            if max_count is not None and len(matched) >= max_count:
                break
        return self._unscope_result(VFSResult(function="glob", entries=matched), user_id)

    async def _vector_search_impl(
        self,
        vector: list[float] | None = None,
        k: int = 15,
        candidates: VFSResult | None = None,
        *,
        user_id: str | None = None,
        session: AsyncSession,
    ) -> VFSResult:
        if self._vector_store is not None:
            return await super()._vector_search_impl(
                vector=vector,
                k=k,
                candidates=candidates,
                user_id=user_id,
                session=session,
            )

        self._require_user_id(user_id)
        candidates = self._scope_candidates(candidates, user_id)
        if vector is None:
            return self._error("vector_search requires a vector")
        if candidates is not None and not candidates.entries:
            return VFSResult(function="vector_search", entries=[])

        vector_spec = postgres_vector_column_spec(self._model)
        vector_type = resolve_embedding_vector_type(self._model)
        distance_operator = _pgvector_distance_operator(vector_spec.operator_class)
        if len(vector) != vector_spec.dimension:
            return self._error(
                "vector_search requires a "
                f"{vector_spec.dimension}-dimension vector for {self._model.__name__}.embedding"
            )

        table = self._resolve_table()
        params: dict[str, object] = {
            "query_vector": vector,
            "k": k,
        }
        candidate_clause = ""
        if candidates is not None:
            params["candidate_paths"] = [entry.path for entry in candidates.entries]
            candidate_clause = "AND o.path = ANY(:candidate_paths)"

        user_scope_clause = ""
        if self._user_scoped and user_id:
            user_scope_clause = "AND o.path LIKE :user_scope ESCAPE '\\'"
            params["user_scope"] = f"/{user_id}/%"

        sql = text(f"""
            SELECT o.path, o.{vector_spec.column_name} {distance_operator} :query_vector AS distance
            FROM {table} AS o
            WHERE o.deleted_at IS NULL
              AND o.{vector_spec.column_name} IS NOT NULL
              {candidate_clause}
              {user_scope_clause}
            ORDER BY o.{vector_spec.column_name} {distance_operator} :query_vector, o.path
            LIMIT :k
        """)
        bind_params = [bindparam("query_vector", type_=vector_type.pgvector_sqlalchemy_type())]
        if candidates is not None:
            bind_params.append(bindparam("candidate_paths", type_=cast("Any", ARRAY(Text()))))
        sql = sql.bindparams(*bind_params)
        rows = (await session.execute(sql, params)).all()
        result = VFSResult(
            function="vector_search",
            entries=[
                Entry(
                    path=row.path,
                    score=_pgvector_distance_to_score(vector_spec.operator_class, float(row.distance)),
                )
                for row in rows
            ],
        )
        return self._unscope_result(result, user_id)

    async def _semantic_search_impl(
        self,
        query: str,
        k: int = 15,
        candidates: VFSResult | None = None,
        *,
        user_id: str | None = None,
        session: AsyncSession,
    ) -> VFSResult:
        if self._vector_store is not None:
            return await super()._semantic_search_impl(
                query,
                k=k,
                candidates=candidates,
                user_id=user_id,
                session=session,
            )

        self._require_user_id(user_id)
        if self._embedding_provider is None:
            return self._error("semantic_search requires an embedding provider")
        if not query or not query.strip():
            return self._error("semantic_search requires a query")

        vector = await self._embedding_provider.embed(query)
        result = await self._vector_search_impl(
            vector=list(vector),
            k=k,
            candidates=candidates,
            user_id=user_id,
            session=session,
        )
        return result.model_copy(update={"function": "semantic_search"})
