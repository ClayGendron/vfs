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
from typing import TYPE_CHECKING, ClassVar

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


def _python_regex_to_postgres(pattern: str) -> str:
    """Translate the small regex subset we synthesize into Postgres ARE syntax."""
    translated = pattern.replace(r"\b", r"\y")
    translated = translated.replace(r"\A", "^").replace(r"\Z", "$")
    translated = translated.replace("(?:", "(")
    return translated


def _parse_vector_dimension(formatted_type: str | None) -> int | None:
    """Extract ``N`` from ``vector(N)``."""
    if formatted_type is None:
        return None
    match = re.fullmatch(r"vector\((\d+)\)", formatted_type.strip())
    if match is None:
        return None
    return int(match.group(1))


class PostgresFileSystem(DatabaseFileSystem):
    """PostgreSQL-native backend with FTS, regex pushdown, and pgvector."""

    FULLTEXT_CONFIG: ClassVar[str] = "simple"
    VECTOR_INDEX_METHODS: ClassVar[tuple[str, ...]] = ("hnsw", "ivfflat")

    def _resolve_table(self) -> str:
        """Return the schema-qualified table name for raw ``text()`` SQL."""
        table = str(self._model.__tablename__)
        return f"{self._schema}.{table}" if self._schema else table

    async def verify_native_search_schema(self) -> None:
        """Confirm the database has the native artifacts required by this backend."""
        async with self._use_session() as session:
            await self._verify_fulltext_schema(session)
            if self._vector_store is None:
                await self._verify_vector_schema(session)

    async def _verify_fulltext_schema(self, session: AsyncSession) -> None:
        if getattr(self, "_native_fulltext_verified", False):
            return

        table = self._resolve_table()
        bare_table = str(self._model.__tablename__)
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

        fulltext_index_exists = (
            await session.execute(
                text(
                    "SELECT 1 "
                    "FROM pg_index AS i "
                    "JOIN pg_class AS idx ON idx.oid = i.indexrelid "
                    "JOIN pg_am AS am ON am.oid = idx.relam "
                    "LEFT JOIN pg_attribute AS att "
                    "  ON att.attrelid = i.indrelid AND att.attnum = ANY(i.indkey) "
                    "LEFT JOIN pg_attrdef AS def "
                    "  ON def.adrelid = att.attrelid AND def.adnum = att.attnum "
                    "WHERE i.indrelid = :oid "
                    "  AND am.amname = 'gin' "
                    "  AND ("
                    "    ("
                    "      coalesce(pg_get_expr(i.indexprs, i.indrelid), '') ILIKE '%to_tsvector%' "
                    "      AND coalesce(pg_get_expr(i.indexprs, i.indrelid), '') ILIKE '%content%' "
                    "      AND coalesce(pg_get_expr(i.indexprs, i.indrelid), '') ILIKE '%simple%'"
                    "    ) "
                    "    OR ("
                    "      att.attgenerated = 's' "
                    "      AND format_type(att.atttypid, att.atttypmod) = 'tsvector' "
                    "      AND coalesce(pg_get_expr(def.adbin, def.adrelid), '') ILIKE '%to_tsvector%' "
                    "      AND coalesce(pg_get_expr(def.adbin, def.adrelid), '') ILIKE '%content%' "
                    "      AND coalesce(pg_get_expr(def.adbin, def.adrelid), '') ILIKE '%simple%'"
                    "    )"
                    "  ) "
                    "LIMIT 1"
                ),
                {"oid": object_id},
            )
        ).scalar()
        if fulltext_index_exists is None:
            raise RuntimeError(
                f"PostgresFileSystem requires a GIN full-text index on '{table}.content'. "
                "Provision one outside the application, for example:\n"
                f"  CREATE INDEX ix_{bare_table}_content_tsv_gin\n"
                f"  ON {table} USING GIN (to_tsvector('{self.FULLTEXT_CONFIG}', coalesce(content, '')));"
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
                text(
                    "SELECT format_type(atttypid, atttypmod) "
                    "FROM pg_attribute "
                    "WHERE attrelid = :oid AND attname = :column AND NOT attisdropped"
                ),
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
                text(
                    "SELECT 1 "
                    "FROM pg_index AS i "
                    "JOIN pg_class AS idx ON idx.oid = i.indexrelid "
                    "JOIN pg_am AS am ON am.oid = idx.relam "
                    "JOIN pg_attribute AS att ON att.attrelid = i.indrelid AND att.attnum = ANY(i.indkey) "
                    "JOIN pg_opclass AS opc ON opc.oid = ANY(i.indclass) "
                    "WHERE i.indrelid = :oid "
                    "  AND att.attname = :column "
                    "  AND am.amname = ANY(:methods) "
                    "  AND opc.opcname = :opclass "
                    "LIMIT 1"
                ).bindparams(
                    bindparam("methods", type_=ARRAY(Text())),
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

    def _build_structural_sql(
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
        """Compose rg-style structural filters for Postgres text SQL."""
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
            for i, value in enumerate(ext):
                params[f"gext{i}"] = value

        if ext_not:
            in_list = ", ".join(f":gextn{i}" for i in range(len(ext_not)))
            clauses.append(f"{ext_col} NOT IN ({in_list})")
            for i, value in enumerate(ext_not):
                params[f"gextn{i}"] = value

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
                pg_regex = _python_regex_to_postgres(regex.pattern)
                like = glob_to_sql_like(scoped)
                if like is not None:
                    glob_or.append(f"({col} LIKE :ggl{i} ESCAPE '\\' AND {col} ~ :ggr{i})")
                    params[f"ggl{i}"] = like
                else:
                    glob_or.append(f"{col} ~ :ggr{i}")
                params[f"ggr{i}"] = pg_regex
            if glob_or:
                clauses.append("(" + " OR ".join(glob_or) + ")")

        if globs_not:
            for i, raw in enumerate(globs_not):
                scoped = self._scope_filter_prefix(raw, user_id)
                regex = compile_glob(scoped)
                if regex is None:
                    continue
                clauses.append(f"NOT ({col} ~ :ggnr{i})")
                params[f"ggnr{i}"] = _python_regex_to_postgres(regex.pattern)

        if not clauses:
            return "", params
        return " AND " + " AND ".join(clauses), params

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
        await self._verify_fulltext_schema(session)
        if not query or not query.strip():
            return self._error("lexical_search requires a query")

        terms = tokenize_query(query)
        if not terms:
            return self._error("lexical_search: no searchable terms in query")

        table = self._resolve_table()
        tsquery = _build_tsquery(list(dict.fromkeys(terms)), operator="|")
        params: dict[str, object] = {"tsquery": tsquery, "k": k}
        user_scope_clause = ""
        if self._user_scoped and user_id:
            user_scope_clause = "AND o.path LIKE :user_scope ESCAPE '\\'"
            params["user_scope"] = f"/{user_id}/%"

        ranking_sql = text(f"""
            WITH query AS (
                SELECT to_tsquery('{self.FULLTEXT_CONFIG}', :tsquery) AS q
            )
            SELECT o.path, o.kind, ts_rank_cd(
                to_tsvector('{self.FULLTEXT_CONFIG}', coalesce(o.content, '')),
                query.q
            ) AS score
            FROM {table} AS o
            CROSS JOIN query
            WHERE o.kind != 'version'
              AND o.deleted_at IS NULL
              AND o.content IS NOT NULL
              AND to_tsvector('{self.FULLTEXT_CONFIG}', coalesce(o.content, '')) @@ query.q
              {user_scope_clause}
            ORDER BY score DESC, o.path
            LIMIT :k
        """)
        rows = (await session.execute(ranking_sql, params)).all()
        if not rows:
            return VFSResult(function="lexical_search", entries=[])

        scored_paths = [(row.path, row.kind, float(row.score)) for row in rows]
        top_paths = [path for path, _kind, _score in scored_paths]
        content_rows = (
            await session.execute(
                text(f"""
                    SELECT path, content
                    FROM {table}
                    WHERE path = ANY(:paths)
                      AND deleted_at IS NULL
                """).bindparams(bindparam("paths", type_=ARRAY(Text()))),
                {"paths": top_paths},
            )
        ).all()
        content_by_path = {row.path: row.content for row in content_rows}

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

        cols = self._resolve_columns("grep", columns) | {"content"}
        self._require_user_id(user_id)
        await self._verify_fulltext_schema(session)
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
        select_set = frozenset({"path"}) if files_only else cols | {"content"}
        select_cols = ", ".join(f"o.{column}" for column in sorted(select_set))

        params: dict[str, object] = dict(filter_params)
        regex_clause = ""
        literal_clause = ""
        if not invert_match:
            regex_operator = "~*" if _regex_flags_for_mode(case_mode, pattern) & re.IGNORECASE else "~"
            params["pattern"] = _python_regex_to_postgres(regex.pattern)
            regex_clause = (
                "AND EXISTS ("
                "  SELECT 1 "
                "  FROM regexp_split_to_table(o.content, E'\\n') AS line "
                f"  WHERE line {regex_operator} :pattern"
                ")"
            )
            literal_terms = _extract_literal_terms(regex.pattern)
            if literal_terms:
                params["literal_query"] = _build_tsquery(literal_terms, operator="&")
                literal_clause = (
                    f"AND to_tsvector('{self.FULLTEXT_CONFIG}', coalesce(o.content, '')) "
                    f"@@ to_tsquery('{self.FULLTEXT_CONFIG}', :literal_query)"
                )

        limit_clause = ""
        if files_only and max_count is not None:
            limit_clause = "LIMIT :max_count"
            params["max_count"] = max_count

        sql = text(f"""
            SELECT {select_cols}
            FROM {table} AS o
            WHERE o.kind = 'file'
              AND o.deleted_at IS NULL
              AND o.content IS NOT NULL
              {literal_clause}
              {regex_clause}
              {filter_clause}
            ORDER BY o.path
            {limit_clause}
        """)
        rows = (await session.execute(sql, params)).all()

        if files_only:
            return self._unscope_result(
                VFSResult(function="grep", entries=[Entry(path=row.path, kind="file") for row in rows]),
                user_id,
            )

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

        if paths:
            merged_paths = paths
        elif decomposition.prefix is not None:
            merged_paths = (decomposition.prefix,)
        else:
            merged_paths = ()

        table = self._resolve_table()
        like_pattern = glob_to_sql_like(pattern)
        like_clause = "AND path LIKE :like_pattern ESCAPE '\\'" if like_pattern is not None else ""

        filter_clause, filter_params = self._build_structural_sql(
            ext=merged_ext,
            ext_not=(),
            paths=merged_paths,
            globs=(),
            globs_not=(),
            user_id=user_id,
            alias="",
        )

        params: dict[str, object] = dict(filter_params)
        limit_clause = ""
        if max_count is not None:
            limit_clause = "LIMIT :max_count"
            params["max_count"] = max_count
        if like_pattern is not None:
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
              {filter_clause}
            ORDER BY path
            {limit_clause}
        """)
        rows = (await session.execute(sql, params)).all()
        matched = [self._row_to_entry(row, cols) for row in rows]
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

        await self._verify_vector_schema(session)
        vector_spec = postgres_vector_column_spec(self._model)
        vector_type = resolve_embedding_vector_type(self._model)
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
            SELECT o.path, (1 - (o.{vector_spec.column_name} <=> :query_vector)) AS score
            FROM {table} AS o
            WHERE o.deleted_at IS NULL
              AND o.{vector_spec.column_name} IS NOT NULL
              {candidate_clause}
              {user_scope_clause}
            ORDER BY o.{vector_spec.column_name} <=> :query_vector, o.path
            LIMIT :k
        """)
        bind_params = [bindparam("query_vector", type_=vector_type.pgvector_sqlalchemy_type())]
        if candidates is not None:
            bind_params.append(bindparam("candidate_paths", type_=ARRAY(Text())))
        sql = sql.bindparams(*bind_params)
        rows = (await session.execute(sql, params)).all()
        result = VFSResult(
            function="vector_search",
            entries=[Entry(path=row.path, score=float(row.score)) for row in rows],
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
