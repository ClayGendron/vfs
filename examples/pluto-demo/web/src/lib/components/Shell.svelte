<script lang="ts">
  import { tick } from "svelte";
  import { api, verbTone, type LogEntry } from "../api";
  import { workspace, type LogLine } from "../state.svelte";

  let { onchanged }: { onchanged: () => void } = $props();

  let input = $state("");
  let history = $state<string[]>([]);
  let cursor = $state(-1);
  let busy = $state(false);
  let height = $state(240);
  let scroller = $state<HTMLElement | null>(null);
  let field = $state<HTMLInputElement | null>(null);

  const welcome: LogLine = {
    key: "welcome",
    ts: 0,
    principal: "",
    actor: "",
    command: "",
    verb: "",
    ok: true,
    elapsed_ms: 0,
    output: "Halyard workspace shell. Type help.",
    fresh: false,
  };

  const lines = $derived([welcome, ...workspace.log]);

  function nameOf(id: string): string {
    return workspace.principals.find((p) => p.id === id)?.name ?? id;
  }

  async function scrollToEnd() {
    await tick();
    if (scroller) scroller.scrollTop = scroller.scrollHeight;
  }

  $effect(() => {
    void lines.length;
    scrollToEnd();
  });

  async function run(event: SubmitEvent) {
    event.preventDefault();
    const command = input.trim();
    if (!command || busy) return;
    busy = true;
    history = [command, ...history.filter((h) => h !== command)].slice(0, 100);
    cursor = -1;
    input = "";
    try {
      const reply = await api.shell(command);
      const entry: LogEntry = {
        ts: reply.ts,
        principal: reply.principal,
        actor: reply.actor,
        command: reply.command,
        verb: reply.verb,
        ok: reply.ok,
        elapsed_ms: reply.elapsed_ms,
        output: reply.output,
      };
      workspace.mergeLog([entry]);
      // The server's log is authoritative; a su changes the principal, a write changes the tree.
      await workspace.pollLog();
      if (reply.principal !== workspace.principal || /^(write|edit|mkdir|rm|grant|revoke|link|su)\b/.test(command)) {
        await workspace.refresh();
        onchanged();
      }
    } catch (e) {
      workspace.mergeLog([
        {
          ts: Date.now() / 1000,
          principal: workspace.principal,
          actor: workspace.principal,
          command,
          verb: "",
          ok: false,
          elapsed_ms: 0,
          output: `ERROR ${e instanceof Error ? e.message : String(e)}`,
        },
      ]);
    } finally {
      busy = false;
      field?.focus();
    }
  }

  function onKey(e: KeyboardEvent) {
    if (e.key === "ArrowUp") {
      e.preventDefault();
      if (history.length === 0) return;
      cursor = Math.min(cursor + 1, history.length - 1);
      input = history[cursor];
    } else if (e.key === "ArrowDown") {
      e.preventDefault();
      cursor = Math.max(cursor - 1, -1);
      input = cursor === -1 ? "" : history[cursor];
    }
  }

  function startResize(e: PointerEvent) {
    const startY = e.clientY;
    const startH = height;
    const move = (ev: PointerEvent) => {
      height = Math.max(120, Math.min(window.innerHeight * 0.8, startH + (startY - ev.clientY)));
    };
    const up = () => {
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", up);
    };
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", up);
  }

  export function focus() {
    field?.focus();
  }

  function outputLines(text: string): { text: string; error: boolean }[] {
    return text.split("\n").map((t) => ({ text: t, error: /^\s*ERROR\b/.test(t) }));
  }
</script>

<section class="shell" style:height="{height}px" aria-label="Shell">
  <div class="grip" role="separator" aria-orientation="horizontal" aria-label="Resize the shell" onpointerdown={startResize}></div>
  <div class="log" bind:this={scroller}>
    {#each lines as line (line.key)}
      <div class="entry" class:fresh={line.fresh}>
        {#if line.command}
          <div class="prompt">
            <span class="user">{line.principal}@halyard</span><span class="dollar">$</span>
            <span class="cmd">{line.command}</span>
            {#if line.actor !== line.principal}
              <span class="actor">run by {nameOf(line.actor)} for {nameOf(line.principal)}</span>
            {/if}
            {#if line.elapsed_ms}
              <span class="ms">{line.elapsed_ms.toFixed(1)} ms</span>
            {/if}
          </div>
        {/if}
        {#if line.output}
          <pre class="out tone-{verbTone(line.verb)}" class:failed={!line.ok}>{#each outputLines(line.output) as l, i (i)}<span class:err={l.error}>{l.text}</span>{"\n"}{/each}</pre>
        {/if}
      </div>
    {/each}
  </div>
  <form class="line" onsubmit={run}>
    <span class="user">{workspace.principal || "…"}@halyard</span><span class="dollar">$</span>
    <input
      id="shell-input"
      class="input"
      bind:this={field}
      bind:value={input}
      onkeydown={onKey}
      placeholder="Try: grep -i runway /finance"
      autocomplete="off"
      spellcheck="false"
      disabled={busy}
      aria-label="Shell command"
    />
  </form>
</section>

<style>
  .shell {
    position: relative;
    display: flex;
    flex-direction: column;
    min-height: 0;
    border-top: var(--line-width) solid var(--border);
    background: var(--background);
    color: var(--foreground);
    font-family: "JetBrains Mono Variable", ui-monospace, monospace;
    font-size: 0.8rem;
    line-height: 1.5;
  }
  .grip {
    position: absolute;
    inset: -4px 0 auto;
    height: 8px;
    cursor: row-resize;
  }
  .grip:hover { background: color-mix(in oklab, var(--primary) 30%, transparent); }
  .log {
    flex: 1;
    min-height: 0;
    overflow: auto;
    padding: 0.6rem max(16px, env(safe-area-inset-right, 0px)) 0.4rem max(16px, env(safe-area-inset-left, 0px));
  }
  .entry { margin-bottom: 0.55rem; border-radius: var(--radius); }
  .entry.fresh { animation: arrive 2.4s ease-out both; }
  @keyframes arrive {
    0% { background: color-mix(in oklab, var(--primary) 22%, transparent); }
    100% { background: transparent; }
  }
  .prompt {
    display: flex;
    flex-wrap: wrap;
    align-items: baseline;
    gap: 0.4rem;
    min-width: 0;
  }
  .user { color: var(--muted-foreground); }
  .dollar { color: var(--primary); margin-left: -0.25rem; }
  .cmd { color: var(--foreground); font-weight: 500; word-break: break-word; }
  .actor {
    padding: 0.05rem 0.45rem;
    border-radius: 999px;
    background: var(--accent);
    color: var(--accent-foreground);
    font-family: "Geist Variable", system-ui, sans-serif;
    font-size: 0.72rem;
  }
  .ms {
    margin-left: auto;
    color: var(--muted-foreground);
    font-size: 0.72rem;
    font-variant-numeric: tabular-nums;
  }
  .out {
    margin: 0.25rem 0 0;
    padding: 0.35rem 0.75rem;
    border-left: 3px solid var(--border);
    color: var(--foreground);
    font: inherit;
    white-space: pre-wrap;
    word-break: break-word;
  }
  .tone-find { border-left-color: var(--chart-1); }
  .tone-grep { border-left-color: var(--chart-2); }
  .tone-glean { border-left-color: var(--chart-3); }
  .tone-graph { border-left-color: var(--chart-4); }
  .failed { border-left-color: var(--destructive); }
  .err { color: var(--destructive); }
  .line {
    display: flex;
    align-items: baseline;
    gap: 0.4rem;
    padding: 0.45rem max(16px, env(safe-area-inset-right, 0px)) 0.5rem max(16px, env(safe-area-inset-left, 0px));
    border-top: var(--line-width) solid var(--border);
  }
  .input {
    flex: 1;
    min-width: 0;
    border: 0;
    background: transparent;
    color: var(--foreground);
    font: inherit;
    outline: none;
  }
  .input::placeholder { color: var(--muted-foreground); }
  .line:focus-within { box-shadow: inset 0 var(--focus-width) 0 var(--ring); }
  @media (prefers-reduced-motion: reduce) {
    .entry.fresh { animation: none; background: color-mix(in oklab, var(--primary) 12%, transparent); }
  }
</style>
