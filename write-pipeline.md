# Database write pipeline

Plan-then-execute flow in `src/vfs/storage/backends/database/writes.py`. The
three public builders share one shape: fetch committed state, stage against a
`_Plan` overlay, then hand an error-free plan to `_finish` → `_apply`, which
runs the pinned bulk-statement sequence. Revisions are per-entry monotone:
creates mint 1, guarded updates write base + 1, clobbers and parent bumps
increment SQL-side (`revision = revision + 1`).

```mermaid
flowchart TD
    subgraph entry ["Entry points (backend.py owns the transaction)"]
        write_rows["write_rows()"]
        mkdir_rows["mkdir_rows()"]
        edit_rows["edit_rows()"]
    end

    fetch["_fetch_committed()<br/>one path IN select: targets + ancestors + root"]

    write_rows --> fetch
    mkdir_rows --> fetch
    edit_rows --> fetch

    subgraph staging ["Staging — _Plan (pure, against committed + staged overlay)"]
        put_file["put_file()"]
        put_dir["put_dir()"]
        gates["outside_trash() / within_budget() / parent_gate()<br/>kind_of() resolves staged-over-committed"]
        mint["mint_chain()<br/>stage missing ancestors, shallowest first"]
        stage["stage_create() → revision 1<br/>stage_update() → base + 1, guarded<br/>(_refresh() folds repeat targets)"]
        bump["bump_parent()<br/>committed parents with membership changes"]
    end

    fetch --> put_file
    fetch --> put_dir
    edit_edits["replace() per EditOperation<br/>re-gate through Entry(...)"]
    fetch --> edit_edits --> stage
    put_file --> gates --> mint --> stage --> bump
    put_dir --> gates

    finish{"_finish()<br/>plan.errors empty?"}
    stage --> finish
    finish -- "errors" --> fail["Result(errors=...)<br/>no mutation statement runs"]

    subgraph execute ["Execution — _apply(), pinned statement order"]
        inserts["_insert_creates()<br/>bulk insert (revision 1), parents before children,<br/>chunked by _chunked() / parameter budget"]
        upsert["_upsert_layer()<br/>ON CONFLICT (parent_id, name);<br/>clobber SET revision = revision + 1;<br/>RETURNING id, path, revision"]
        catchretry["_catch_retry_layer()<br/>savepointed bulk insert"]
        resolve["_resolve_rows()<br/>row-at-a-time savepoints;<br/>may convert create → clobbering update"]
        materials["_update_materials()<br/>guarded: base + 1 WHERE revision = base;<br/>unguarded: revision = revision + 1;<br/>one verification read-back"]
        content["_replace_content()<br/>delete-then-insert content rows"]
        bumps["_bump_parents()<br/>revision = revision + 1 WHERE id IN (...);<br/>read-back only when an unchanged<br/>observation needs the bumped value"]
    end

    finish -- "clean" --> inserts
    inserts -- "arbitration = upsert" --> upsert
    inserts -- "arbitration = catch_retry" --> catchretry
    catchretry -- "IntegrityError" --> resolve
    upsert --> materials
    catchretry --> materials
    resolve --> materials
    materials --> content --> bumps

    rowvals["_entry_values() / _parent_id() / _update_params()"]
    inserts -.-> rowvals
    materials -.-> rowvals

    observations["_finish(): assemble Observation rows<br/>from plan.pending + bump_revisions"]
    bumps --> observations --> ok["Result(observations=...)"]

    upsert -- "lost arbitration" --> late["late errors → Result(errors=...)<br/>batch fails whole"]
    resolve -- "conflict / exists / wrong_kind" --> late
    materials -- "guard mismatch / vanished row" --> late
```
