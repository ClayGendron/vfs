<script lang="ts">
  import { api } from "../api";
  import { workspace } from "../state.svelte";

  let rows = $state<string[][]>([]);
  let path = $state<string | null>(null);
  let dirty = $state(false);
  let status = $state("");

  export async function open(p: string) {
    const body = await api.file(p);
    rows = body.content.trim().split(/\r?\n/).map((line) => line.split(","));
    path = p;
    workspace.openPath = p;
    dirty = false;
    status = "";
  }

  function edit(r: number, c: number, value: string) {
    rows[r][c] = value;
    dirty = true;
    status = "";
  }

  async function save() {
    if (!path) return;
    status = "Saving";
    try {
      const reply = await api.save(path, rows.map((r) => r.join(",")).join("\n") + "\n");
      if (!reply.ok) throw new Error(reply.output);
      dirty = false;
      status = "Saved";
    } catch (e) {
      status = e instanceof Error ? e.message : "Save failed";
    }
  }

  function addRow() {
    rows = [...rows, rows[0].map(() => "")];
    dirty = true;
  }

  const numeric = (v: string) => v !== "" && !Number.isNaN(Number(v));
  const title = $derived(path ? path.split("/").pop()!.replace(/\.csv$/, "").replace(/[-_]/g, " ") : "");

  function onKey(e: KeyboardEvent) {
    if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "s") {
      e.preventDefault();
      save();
    }
  }
</script>

<!-- svelte-ignore a11y_no_static_element_interactions -->
<section class="sheet" onkeydown={onKey}>
  {#if path}
    <header class="head">
      <div>
        <h1 class="title">{title}</h1>
        <p class="meta">{rows.length - 1} rows, {rows[0]?.length ?? 0} columns</p>
      </div>
      <div class="tools">
        <span class="status" class:ok={status === "Saved"} aria-live="polite">{status}</span>
        <button type="button" class="plain" onclick={addRow}>Add row</button>
        <button type="button" class="save" onclick={save} disabled={!dirty && status !== ""}>Save</button>
      </div>
    </header>
    <div class="grid-wrap">
      <table class="grid">
        <thead>
          <tr>
            <th class="rownum"></th>
            {#each rows[0] ?? [] as h, c (c)}
              <th><input class="cell head-cell" value={h} oninput={(e) => edit(0, c, e.currentTarget.value)} aria-label="Column {c + 1} name" /></th>
            {/each}
          </tr>
        </thead>
        <tbody>
          {#each rows.slice(1) as row, i (i)}
            <tr>
              <td class="rownum">{i + 1}</td>
              {#each row as value, c (c)}
                <td>
                  <input
                    class="cell"
                    class:num={numeric(value)}
                    {value}
                    oninput={(e) => edit(i + 1, c, e.currentTarget.value)}
                    aria-label="Row {i + 1}, {rows[0][c]}"
                  />
                </td>
              {/each}
            </tr>
          {/each}
        </tbody>
      </table>
    </div>
  {:else}
    <div class="empty"><p>Pick a sheet from the list.</p></div>
  {/if}
</section>

<style>
  .sheet { display: flex; flex-direction: column; min-height: 0; min-width: 0; height: 100%; background: var(--raised); font-family: "Geist Variable", system-ui, sans-serif; }
  .head { display: flex; justify-content: space-between; align-items: flex-end; gap: 1rem; padding: 1.5rem 2rem 1rem; }
  .title { margin: 0; font-size: 1.5rem; font-weight: 600; letter-spacing: -0.02em; text-transform: capitalize; }
  .meta { margin: 0.2rem 0 0; color: var(--muted-foreground); font-size: 0.85rem; font-variant-numeric: tabular-nums; }
  .tools { display: flex; align-items: center; gap: 0.5rem; }
  .status { color: var(--muted-foreground); font-size: 0.8rem; }
  .status.ok { color: var(--success); }
  .plain { padding: 0.4rem 0.7rem; border: var(--line-width) solid var(--border); border-radius: var(--radius); background: transparent; color: var(--foreground); font: inherit; font-size: 0.85rem; cursor: pointer; }
  .save { padding: 0.4rem 0.9rem; border: 0; border-radius: var(--radius); background: var(--primary); color: var(--primary-foreground); font: inherit; font-size: 0.85rem; font-weight: 500; cursor: pointer; }
  .save:disabled { opacity: 0.5; cursor: default; }
  .grid-wrap { flex: 1; min-height: 0; overflow: auto; padding: 0 2rem 2rem; }
  .grid { border-collapse: collapse; font-size: 0.9rem; }
  .grid th, .grid td { border: var(--line-width) solid var(--border); padding: 0; }
  .grid thead th { background: var(--muted); position: sticky; top: 0; z-index: 1; }
  .rownum { width: 2.5rem; padding: 0 0.5rem; color: var(--muted-foreground); text-align: right; font-size: 0.75rem; font-variant-numeric: tabular-nums; background: var(--muted); }
  .cell { width: 100%; min-width: 9rem; padding: 0.45rem 0.7rem; border: 0; background: transparent; color: var(--foreground); font: inherit; font-variant-numeric: tabular-nums; }
  .head-cell { font-weight: 600; }
  .cell.num { text-align: right; }
  .cell:focus { outline: var(--focus-width) solid var(--ring); outline-offset: -2px; background: var(--background); }
  .plain:focus-visible, .save:focus-visible { outline: var(--focus-width) solid var(--ring); outline-offset: var(--focus-offset); }
  .empty { flex: 1; display: grid; place-content: center; color: var(--muted-foreground); }
</style>
