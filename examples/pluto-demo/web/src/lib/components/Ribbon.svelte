<script lang="ts">
  import { Check, Code, FileText, Folders, Moon, PresentationChart, Sparkle, Sun, Table, Terminal } from "phosphor-svelte";
  import FourDot from "./FourDot.svelte";
  import { APPS, workspace, type AppId } from "../state.svelte";

  let accountsOpen = $state(false);
  let switching = $state(false);
  const people = $derived(workspace.principals.filter((p) => p.kind === "user"));
  const initials = $derived((workspace.current?.name ?? "").split(" ").map((w) => w[0]).join("").slice(0, 2));

  async function choose(id: string) {
    accountsOpen = false;
    if (id === workspace.principal) return;
    switching = true;
    try {
      await workspace.switchPrincipal(id);
    } finally {
      switching = false;
    }
  }

  function onWindowKey(e: KeyboardEvent) {
    if (e.key === "Escape") accountsOpen = false;
  }

  const icons = { files: Folders, docs: FileText, sheets: Table, slides: PresentationChart, code: Code, terminal: Terminal } as const;
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
    <div class="account">
      <button
        type="button"
        class="avatar"
        class:busy={switching}
        aria-haspopup="menu"
        aria-expanded={accountsOpen}
        aria-label="Account: {workspace.current?.name ?? ''}"
        title={workspace.current?.name}
        onclick={() => (accountsOpen = !accountsOpen)}
      >
        {initials}
      </button>
      {#if accountsOpen}
        <div class="menu" role="menu" aria-label="Switch account">
          {#each people as p (p.id)}
            <button type="button" class="person" role="menuitemradio" aria-checked={p.id === workspace.principal} onclick={() => choose(p.id)}>
              <span class="person-avatar" aria-hidden="true">{p.name.split(" ").map((w) => w[0]).join("").slice(0, 2)}</span>
              <span class="person-text">
                <span class="person-name">{p.name}</span>
                <span class="person-role">{p.role}</span>
              </span>
              {#if p.id === workspace.principal}<span class="check"><Check size={14} weight="bold" /></span>{/if}
            </button>
          {/each}
        </div>
      {/if}
    </div>
  </div>
</nav>

<svelte:window onkeydown={onWindowKey} />
{#if accountsOpen}
  <button type="button" class="scrim" aria-label="Close account menu" onclick={() => (accountsOpen = false)}></button>
{/if}

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
  .account { position: relative; display: flex; justify-content: center; padding-block: 0.35rem 0.25rem; }
  .avatar {
    display: grid;
    place-items: center;
    width: 32px;
    height: 32px;
    border: 0;
    border-radius: 999px;
    background: var(--primary);
    color: var(--primary-foreground);
    font: inherit;
    font-size: 0.72rem;
    font-weight: 600;
    letter-spacing: 0.02em;
    cursor: pointer;
    transition: opacity var(--motion-micro);
  }
  .avatar.busy { opacity: 0.6; }
  .avatar:focus-visible { outline: var(--focus-width) solid var(--ring); outline-offset: var(--focus-offset); }
  .scrim { position: fixed; inset: 0; z-index: 30; border: 0; background: transparent; cursor: default; }
  .menu {
    position: absolute;
    left: calc(100% + 8px);
    bottom: 0;
    z-index: 40;
    display: flex;
    flex-direction: column;
    gap: 2px;
    min-width: 15rem;
    padding: 0.35rem;
    border: var(--line-width) solid var(--elevation-line);
    border-radius: calc(var(--radius) * 1.5);
    background: var(--popover);
    color: var(--popover-foreground);
    box-shadow: 0 8px 24px var(--elevation-shadow);
  }
  .person {
    display: flex;
    align-items: center;
    gap: 0.6rem;
    width: 100%;
    padding: 0.45rem 0.6rem;
    border: 0;
    border-radius: var(--radius);
    background: transparent;
    color: inherit;
    font: inherit;
    text-align: left;
    cursor: pointer;
  }
  .person:hover { background: var(--accent); }
  .person:focus-visible { outline: var(--focus-width) solid var(--ring); outline-offset: calc(-1 * var(--focus-width)); }
  .person-avatar {
    display: grid;
    place-items: center;
    flex: none;
    width: 28px;
    height: 28px;
    border-radius: 999px;
    background: var(--muted);
    color: var(--foreground);
    font-size: 0.65rem;
    font-weight: 600;
  }
  .person-text { display: flex; flex-direction: column; min-width: 0; line-height: 1.2; }
  .person-name { font-size: 0.875rem; font-weight: 500; }
  .person-role { color: var(--muted-foreground); font-size: 0.75rem; }
  .check { margin-left: auto; display: inline-flex; color: var(--primary); }
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
    .bottom { flex-direction: row; margin-top: 0; width: auto; padding: 0; align-items: center; }
    .menu { left: auto; right: 0; bottom: calc(100% + 8px); }
    .app { padding-block: 0.3rem; }
  }
  @media (prefers-reduced-motion: reduce) {
    .app { transition: none; }
  }
</style>
