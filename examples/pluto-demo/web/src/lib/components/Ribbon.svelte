<script lang="ts">
  import { Code, FileText, Moon, PresentationChart, Sparkle, Sun, Table, Terminal } from "phosphor-svelte";
  import FourDot from "./FourDot.svelte";
  import { APPS, workspace, type AppId } from "../state.svelte";

  const icons = { docs: FileText, sheets: Table, slides: PresentationChart, code: Code, terminal: Terminal } as const;
</script>

<nav class="ribbon" aria-label="Apps">
  <div class="mark"><FourDot entrance label="Pluto Systems" /></div>
  <div class="apps">
    {#each APPS as app (app.id)}
      {@const Icon = icons[app.id as AppId]}
      {@const active = workspace.app === app.id}
      <button
        type="button"
        class="app"
        class:active
        aria-current={active ? "page" : undefined}
        onclick={() => workspace.openApp(app.id)}
      >
        <span class="icon">
          <Icon size={22} weight={active ? "fill" : "regular"} />
          {#if app.id === "terminal" && workspace.agentRuns > 0}
            <span class="count" aria-label="{workspace.agentRuns} new commands">{workspace.agentRuns}</span>
          {/if}
        </span>
        <span class="label">{app.name}</span>
      </button>
    {/each}
  </div>
  <div class="bottom">
    <button
      type="button"
      class="app"
      class:active={workspace.atlasOpen}
      aria-pressed={workspace.atlasOpen}
      onclick={() => (workspace.atlasOpen = !workspace.atlasOpen)}
    >
      <span class="icon"><Sparkle size={22} weight={workspace.atlasOpen ? "fill" : "regular"} /></span>
      <span class="label">Atlas</span>
    </button>
    <button
      type="button"
      class="app theme"
      onclick={() => workspace.setTheme(workspace.theme === "dark" ? "light" : "dark")}
      aria-label={workspace.theme === "dark" ? "Switch to light theme" : "Switch to dark theme"}
    >
      <span class="icon">
        {#if workspace.theme === "dark"}<Sun size={20} />{:else}<Moon size={20} />{/if}
      </span>
    </button>
  </div>
</nav>

<style>
  .ribbon {
    display: flex;
    flex-direction: column;
    align-items: center;
    width: 64px;
    padding: 0.75rem 0 0.5rem;
    border-right: var(--line-width) solid var(--sidebar-border);
    background: var(--sidebar);
    font-family: "Geist Variable", system-ui, sans-serif;
  }
  .mark { font-size: 1.1rem; margin-bottom: 1rem; }
  .apps, .bottom { display: flex; flex-direction: column; gap: 0.25rem; width: 100%; padding-inline: 6px; }
  .bottom { margin-top: auto; }
  .app {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 2px;
    width: 100%;
    padding: 0.45rem 0 0.35rem;
    border: 0;
    border-radius: var(--radius);
    background: transparent;
    color: var(--muted-foreground);
    font: inherit;
    cursor: pointer;
    transition: background var(--motion-micro), color var(--motion-micro);
  }
  .app:hover { background: var(--sidebar-accent); color: var(--foreground); }
  .app.active {
    background: color-mix(in oklab, var(--primary) 12%, transparent);
    color: var(--primary);
  }
  .app:focus-visible { outline: var(--focus-width) solid var(--ring); outline-offset: calc(-1 * var(--focus-width)); }
  .icon { position: relative; display: grid; place-items: center; height: 24px; }
  .label { font-size: 0.65rem; line-height: 1; }
  .theme { padding-block: 0.5rem; }
  .count {
    position: absolute;
    top: -4px;
    right: -10px;
    min-width: 1rem;
    padding: 0 0.3rem;
    border-radius: 999px;
    background: var(--destructive-fill);
    color: var(--destructive-foreground);
    font-size: 0.62rem;
    font-weight: 600;
    line-height: 1rem;
    text-align: center;
    font-variant-numeric: tabular-nums;
  }
  @media (max-width: 900px) {
    .ribbon {
      flex-direction: row;
      width: 100%;
      padding: 0.25rem max(8px, env(safe-area-inset-right, 0px)) max(0.25rem, env(safe-area-inset-bottom, 0px)) max(8px, env(safe-area-inset-left, 0px));
      border-right: 0;
      border-top: var(--line-width) solid var(--sidebar-border);
    }
    .mark { display: none; }
    .apps { flex-direction: row; flex: 1; padding: 0; }
    .bottom { flex-direction: row; margin-top: 0; width: auto; padding: 0; }
    .app { padding-block: 0.3rem; }
  }
  @media (prefers-reduced-motion: reduce) {
    .app { transition: none; }
  }
</style>
