<script lang="ts">
  import { APPS, workspace } from "../state.svelte";
</script>

<header class="topbar">
  <div class="brand">
    <span class="wordmark">Halyard</span>
    <span class="app-name">{APPS.find((a) => a.id === workspace.app)?.name}</span>
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
  @media (max-width: 900px) {
    .topbar { gap: 0.75rem; }
  }
</style>
