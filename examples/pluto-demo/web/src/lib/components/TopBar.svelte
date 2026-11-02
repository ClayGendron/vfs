<script lang="ts">
  import { APPS, workspace } from "../state.svelte";

  let switching = $state(false);

  async function choose(id: string) {
    switching = true;
    try {
      await workspace.switchPrincipal(id);
    } finally {
      switching = false;
    }
  }
</script>

<header class="topbar">
  <div class="brand">
    <span class="wordmark">Halyard</span>
    <span class="app-name">{APPS.find((a) => a.id === workspace.app)?.name}</span>
  </div>

  <div class="who" role="group" aria-label="Signed in as">
    <span class="who-label">Working as</span>
    <div class="segmented" class:busy={switching}>
      {#each workspace.principals.filter((p) => p.kind === "user") as p (p.id)}
        <button
          type="button"
          class="seg"
          class:active={p.id === workspace.principal}
          aria-pressed={p.id === workspace.principal}
          onclick={() => choose(p.id)}
          title={p.role}
        >
          <span class="seg-name">{p.name}</span>
          <span class="seg-role">{p.role}</span>
        </button>
      {/each}
    </div>
  </div>

  <div class="right">
    <span class="index" title="Which legs glean can rank with">
      <span class="index-dot" class:semantic={workspace.embedder === "model2vec"}></span>
      {workspace.embedder === "model2vec" ? "Semantic index ready" : "Lexical index only"}
    </span>
  </div>
</header>

<style>
  .topbar {
    display: flex;
    align-items: center;
    gap: 1.5rem;
    height: 3rem;
    padding-inline: max(16px, env(safe-area-inset-left, 0px)) max(16px, env(safe-area-inset-right, 0px));
    border-bottom: var(--line-width) solid var(--border);
    background: var(--background);
    font-family: "Geist Variable", system-ui, sans-serif;
  }
  .brand {
    display: inline-flex;
    align-items: baseline;
    gap: 0.5rem;
    color: var(--foreground);
    font-size: 0.95rem;
  }
  .wordmark { font-weight: 600; letter-spacing: -0.01em; }
  .app-name { color: var(--muted-foreground); }
  .app-name::before { content: "/ "; }
  .who {
    display: flex;
    align-items: center;
    gap: 0.75rem;
    min-width: 0;
  }
  .who-label {
    color: var(--muted-foreground);
    font-size: 0.85rem;
  }
  .segmented {
    display: inline-flex;
    padding: 2px;
    border-radius: calc(var(--radius) + 2px);
    background: var(--muted);
    transition: opacity var(--motion-micro);
  }
  .busy { opacity: 0.6; }
  .seg {
    display: flex;
    flex-direction: column;
    align-items: flex-start;
    gap: 0;
    padding: 0.3rem 0.75rem;
    border: 0;
    border-radius: var(--radius);
    background: transparent;
    color: var(--muted-foreground);
    font: inherit;
    line-height: 1.15;
    cursor: pointer;
    text-align: left;
    transition: background var(--motion-micro), color var(--motion-micro);
  }
  .seg:hover { color: var(--foreground); }
  .seg.active {
    background: var(--raised);
    color: var(--foreground);
    box-shadow: 0 1px 2px var(--elevation-shadow);
  }
  .seg-name { font-size: 0.85rem; font-weight: 500; }
  .seg-role { font-size: 0.7rem; color: var(--muted-foreground); }
  .right {
    margin-left: auto;
    display: flex;
    align-items: center;
    gap: 1rem;
  }
  .index {
    display: inline-flex;
    align-items: center;
    gap: 0.45rem;
    font-size: 0.8rem;
    color: var(--muted-foreground);
  }
  .index-dot {
    width: 0.5rem;
    height: 0.5rem;
    border-radius: 999px;
    background: var(--caution);
  }
  .index-dot.semantic { background: var(--success-fill); }
  .seg:focus-visible {
    outline: var(--focus-width) solid var(--ring);
    outline-offset: var(--focus-offset);
  }
  @media (max-width: 900px) {
    .who-label, .seg-role, .index { display: none; }
    .topbar { gap: 0.75rem; }
  }
</style>
