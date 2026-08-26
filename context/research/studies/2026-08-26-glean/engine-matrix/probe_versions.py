"""Probe 1: engine versions and raw capability presence (vector type, distance fn, FTS)."""

from __future__ import annotations

import asyncio
import sys

sys.path.insert(0, __file__.rsplit("/", 1)[0])
from probe_common import dump, run  # noqa: E402

PROBES = {
    "postgres_compose": [
        ("version", "select version()"),
        ("pgvector_available", "select count(*) from pg_available_extensions where name='vector'"),
        ("create_ext", "create extension if not exists vector"),
    ],
    "pgvector": [
        ("version", "select version()"),
        ("create_ext", "create extension if not exists vector"),
        ("ext_version", "select extversion from pg_extension where extname='vector'"),
        ("cosine", "select '[1,0,0]'::vector <=> '[0,1,0]'::vector"),
        ("ts_rank", "select ts_rank(to_tsvector('english','the quick brown fox'), plainto_tsquery('english','fox'))"),
        ("ts_rank_cd", "select ts_rank_cd(to_tsvector('english','the quick brown fox'), plainto_tsquery('english','fox'))"),
    ],
    "mysql9": [
        ("version", "select version()"),
        ("vector_type", "create table glean_v (id int primary key, v vector(3))"),
        ("insert", "insert into glean_v values (1, string_to_vector('[1,0,0]'))"),
        ("vector_dim", "select vector_dim(v), vector_to_string(v), length(v) from glean_v"),
        ("distance_fn", "select distance(v, string_to_vector('[0,1,0]'), 'COSINE') from glean_v"),
        ("vector_distance_fn", "select vector_distance(v, string_to_vector('[0,1,0]'), 'COSINE') from glean_v"),
        ("vector_index", "create index vi on glean_v (v)"),
        ("fulltext", "create table glean_ft (id int primary key, body text, fulltext (body)) engine=innodb"),
        ("ft_insert", "insert into glean_ft values (1,'the quick brown fox'),(2,'lazy dog'),(3,'fox fox fox')"),
        ("ft_score", "select id, match(body) against ('fox' in natural language mode) as s from glean_ft order by s desc"),
        ("drop1", "drop table glean_v"),
        ("drop2", "drop table glean_ft"),
    ],
    "mariadb118": [
        ("version", "select version()"),
        ("vector_type", "create table glean_v (id int primary key, v vector(3) not null, vector index (v) distance=cosine)"),
        ("insert", "insert into glean_v values (1, vec_fromtext('[1,0,0]')),(2, vec_fromtext('[0,1,0]')),(3, vec_fromtext('[0.7,0.7,0]'))"),
        ("cosine", "select id, vec_distance_cosine(v, vec_fromtext('[1,0,0]')) d from glean_v order by d limit 3"),
        ("vec_distance", "select id, vec_distance(v, vec_fromtext('[1,0,0]')) d from glean_v order by d limit 3"),
        ("explain_knn", "explain select id from glean_v order by vec_distance_cosine(v, vec_fromtext('[1,0,0]')) limit 2"),
        ("fulltext", "create table glean_ft (id int primary key, body text, fulltext (body)) engine=innodb"),
        ("ft_insert", "insert into glean_ft values (1,'the quick brown fox'),(2,'lazy dog'),(3,'fox fox fox')"),
        ("ft_score", "select id, match(body) against ('fox' in natural language mode) as s from glean_ft order by s desc"),
        ("drop1", "drop table glean_v"),
        ("drop2", "drop table glean_ft"),
    ],
    "mssql2025": [
        ("version", "select @@version"),
        ("vector_type", "create table glean_v (id int primary key, v vector(3))"),
        ("insert", "insert into glean_v values (1,'[1,0,0]'),(2,'[0,1,0]'),(3,'[0.7,0.7,0]')"),
        ("cosine", "select id, vector_distance('cosine', v, cast('[1,0,0]' as vector(3))) d from glean_v order by d"),
        ("fts_installed", "select fulltextserviceproperty('IsFullTextInstalled')"),
        ("preview_flag", "select name, value from sys.database_scoped_configurations where name='PREVIEW_FEATURES'"),
        ("drop1", "drop table glean_v"),
    ],
    "oracle23": [
        ("version", "select banner_full from v$version"),
        ("registry", "select comp_id, status from dba_registry"),
        ("ctxsys", "select count(*) from all_users where username='CTXSYS'"),
        ("vector_type", "create table glean_v (id number primary key, v vector(3, float32))"),
        ("insert", "insert into glean_v values (1, '[1,0,0]')"),
        ("cosine", "select vector_distance(v, to_vector('[0,1,0]'), cosine) from glean_v"),
        ("hybrid_pkg", "select count(*) from all_objects where object_name='DBMS_HYBRID_VECTOR'"),
        ("drop1", "drop table glean_v"),
    ],
    "sqlite": [
        ("version", "select sqlite_version()"),
        ("vec_version", "select vec_version()"),
        ("fts5", "select sqlite_compileoption_used('ENABLE_FTS5')"),
        ("cosine", "select vec_distance_cosine('[1,0,0]', '[0,1,0]')"),
    ],
}


async def main():
    results = {}
    for name, steps in PROBES.items():
        try:
            results[name] = await run(name, steps)
        except Exception as exc:  # noqa: BLE001
            print(f"[{name}] CONNECT FAILED: {type(exc).__name__}: {str(exc)[:300]}")
            results[name] = {"connect_error": str(exc)[:300]}
    dump(__file__.rsplit("/", 1)[0] + "/results_versions.json", results)


asyncio.run(main())
