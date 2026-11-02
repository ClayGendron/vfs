<script lang="ts">
  import { tick } from "svelte";
  import { marked } from "marked";
  import { api, verbOf, verbTone, type ChatTurn } from "../api";
  import { workspace } from "../state.svelte";

  type ToolCall = { id: string; command: string; output: string; ok: boolean; verb: string; elapsed_ms: number; done: boolean; open: boolean };
  type Block = { kind: "text"; text: string } | { kind: "tool"; call: ToolCall };
  type Message = { id: number; role: "user" | "assistant"; blocks: Block[]; mode?: "live" | "scripted"; error?: string };

  let messages = $state<Message[]>([]);
  let draft = $state("");
  let thinking = $state(false);
  let scroller = $state<HTMLElement | null>(null);
  let seq = 0;

  let { onchanged, onclose }: { onchanged: () => void; onclose?: () => void } = $props();

  const suggestions = [
    "What did we decide about the gripper firmware?",
    "How much runway do we have?",
    "Draft an onboarding note for Sam from the handbook",
    "Which customers are affected by the actuator recall?",
  ];

  function history(): ChatTurn[] {
    return messages
      .filter((m) => !m.error)
      .map((m) => ({
        role: m.role,
        content: m.blocks.map((b) => (b.kind === "text" ? b.text : `$ ${b.call.command}\n${b.call.output}`)).join("\n"),
      }));
  }

  async function scrollToEnd() {
    await tick();
    if (scroller) scroller.scrollTop = scroller.scrollHeight;
  }

  async function send(text: string) {
    const message = text.trim();
    if (!message || thinking) return;
    const past = history();
    draft = "";
    messages = [...messages, { id: ++seq, role: "user", blocks: [{ kind: "text", text: message }] }];
    messages = [...messages, { id: ++seq, role: "assistant", blocks: [] }];
    // Mutate the proxied copy the state array holds, so Svelte sees every delta.
    const reply = messages[messages.length - 1];
    thinking = true;
    scrollToEnd();
    let touched = false;
    try {
      for await (const ev of api.chat(message, past)) {
        if (ev.event === "text") {
          const last = reply.blocks.at(-1);
          if (last && last.kind === "text") last.text += ev.data.delta;
          else reply.blocks.push({ kind: "text", text: ev.data.delta });
        } else if (ev.event === "tool") {
          for (const b of reply.blocks) if (b.kind === "tool") b.call.open = false;
          reply.blocks.push({
            kind: "tool",
            call: { id: ev.data.id, command: ev.data.command, output: "", ok: true, verb: verbOf(ev.data.command), elapsed_ms: 0, done: false, open: true },
          });
          if (/^(write|edit|mkdir|rm|grant|revoke|link)\b/.test(ev.data.command)) touched = true;
        } else if (ev.event === "result") {
          const block = reply.blocks.find((b) => b.kind === "tool" && b.call.id === ev.data.id);
          if (block && block.kind === "tool") {
            block.call.output = ev.data.output;
            block.call.ok = ev.data.ok;
            block.call.verb = ev.data.verb || block.call.verb;
            block.call.elapsed_ms = ev.data.elapsed_ms;
            block.call.done = true;
          }
          workspace.pollLog();
        } else if (ev.event === "done") {
          reply.mode = ev.data.mode;
        } else if (ev.event === "error") {
          reply.error = ev.data.message;
        }
        scrollToEnd();
      }
    } catch (e) {
      reply.error = e instanceof Error ? e.message : String(e);
    } finally {
      thinking = false;
      await workspace.pollLog();
      if (touched) {
        await workspace.refresh();
        onchanged();
      }
      scrollToEnd();
    }
  }

  function onKey(e: KeyboardEvent) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      send(draft);
    }
  }

  function render(text: string): string {
    return marked.parse(text, { async: false }) as string;
  }
</script>

<section class="chat" aria-label="Atlas, the workspace agent">
  <header class="head">
    <span class="avatar" aria-hidden="true">A</span>
    <div class="head-text">
      <span class="name">Atlas</span>
      <span class="sub">Workspace agent</span>
    </div>
    {#if onclose}
      <button type="button" class="close" onclick={onclose} aria-label="Close Atlas">×</button>
    {/if}
  </header>

  <div class="list" bind:this={scroller}>
    {#if messages.length === 0}
      <div class="suggest">
        {#each suggestions as s (s)}
          <button type="button" class="chip" onclick={() => send(s)}>{s}</button>
        {/each}
      </div>
    {/if}
    {#each messages as m (m.id)}
      <div class="msg {m.role}">
        {#each m.blocks as block, i (i)}
          {#if block.kind === "text"}
            {#if m.role === "user"}
              <p class="bubble">{block.text}</p>
            {:else}
              <div class="prose">{@html render(block.text)}</div>
            {/if}
          {:else}
            <details class="call tone-{verbTone(block.call.verb)}" class:failed={!block.call.ok} open={block.call.open}>
              <summary class="call-summary">
                <span class="dollar">$</span>
                <span class="call-cmd">{block.call.command}</span>
                {#if !block.call.done}
                  <span class="running" aria-label="running"></span>
                {:else}
                  <span class="call-ms">{block.call.elapsed_ms.toFixed(1)} ms</span>
                {/if}
              </summary>
              {#if block.call.done}
                <pre class="call-out">{block.call.output || "(no output)"}</pre>
              {/if}
            </details>
          {/if}
        {/each}
        {#if m.error}
          <p class="error">{m.error}</p>
        {/if}
      </div>
    {/each}
    {#if thinking}
      <div class="thinking" aria-live="polite">
        <span></span><span></span><span></span>
      </div>
    {/if}
  </div>

  {#if workspace.agentRuns > 0 && workspace.app !== "terminal"}
    <button type="button" class="ran" onclick={() => workspace.openApp("terminal")}>
      {workspace.agentRuns} {workspace.agentRuns === 1 ? "command" : "commands"} ran in Terminal
    </button>
  {/if}

  <form class="composer" onsubmit={(e) => { e.preventDefault(); send(draft); }}>
    <textarea
      id="chat-draft"
      class="draft"
      bind:value={draft}
      onkeydown={onKey}
      rows="2"
      placeholder="Ask Atlas"
      aria-label="Message to Atlas"
      disabled={thinking}
    ></textarea>
    <button type="submit" class="send" disabled={thinking || !draft.trim()}>Send</button>
  </form>
</section>

<style>
  .chat {
    display: flex;
    flex-direction: column;
    min-height: 0;
    min-width: 0;
    height: 100%;
    border-left: var(--line-width) solid var(--border);
    background: var(--background);
    font-family: "Geist Variable", system-ui, sans-serif;
  }
  .head {
    display: flex;
    align-items: center;
    gap: 0.6rem;
    padding: 0.65rem 1rem;
    border-bottom: var(--line-width) solid var(--border);
  }
  .avatar {
    display: grid;
    place-items: center;
    width: 1.8rem;
    height: 1.8rem;
    border-radius: 999px;
    background: var(--foreground);
    color: var(--background);
    font-size: 0.85rem;
    font-weight: 600;
  }
  .close { margin-left: auto; padding: 0.2rem 0.5rem; border: 0; background: transparent; color: var(--muted-foreground); font: inherit; font-size: 1.2rem; cursor: pointer; }
  .close:focus-visible { outline: var(--focus-width) solid var(--ring); outline-offset: var(--focus-offset); }
  .head-text { display: flex; flex-direction: column; min-width: 0; line-height: 1.2; }
  .name { font-weight: 600; font-size: 0.9rem; }
  .sub { color: var(--muted-foreground); font-size: 0.75rem; }
  .list {
    flex: 1;
    min-height: 0;
    overflow: auto;
    display: flex;
    flex-direction: column;
    gap: 0.9rem;
    padding: 1rem;
  }
  .suggest { display: flex; flex-direction: column; gap: 0.5rem; margin-top: 0.5rem; }
  .suggest-lead { margin: 0 0 0.5rem; color: var(--muted-foreground); font-size: 0.9rem; line-height: 1.45; }
  .chip {
    padding: 0.5rem 0.75rem;
    border: var(--line-width) solid var(--border);
    border-radius: var(--radius);
    background: var(--raised);
    color: var(--foreground);
    font: inherit;
    font-size: 0.85rem;
    text-align: left;
    cursor: pointer;
    transition: border-color var(--motion-micro);
  }
  .chip:hover { border-color: var(--primary); }
  .msg { display: flex; flex-direction: column; gap: 0.5rem; min-width: 0; }
  .msg.user { align-items: flex-end; }
  .bubble {
    max-width: 85%;
    margin: 0;
    padding: 0.55rem 0.8rem;
    border-radius: var(--radius);
    background: var(--primary);
    color: var(--primary-foreground);
    font-size: 0.9rem;
    line-height: 1.45;
    white-space: pre-wrap;
    word-break: break-word;
  }
  .prose { font-size: 0.9rem; line-height: 1.55; min-width: 0; }
  .prose :global(p) { margin: 0 0 0.6rem; }
  .prose :global(p:last-child) { margin-bottom: 0; }
  .prose :global(ul), .prose :global(ol) { margin: 0 0 0.6rem; padding-left: 1.2rem; }
  .prose :global(code) { font-family: "JetBrains Mono Variable", ui-monospace, monospace; font-size: 0.85em; background: var(--code-background); padding: 0.05em 0.3em; border-radius: 3px; }
  .prose :global(pre) { overflow-x: auto; padding: 0.6rem 0.75rem; border-radius: var(--radius); background: var(--code-background); }
  .prose :global(pre code) { background: transparent; padding: 0; }
  .prose :global(h1), .prose :global(h2), .prose :global(h3) { font-size: 0.95rem; margin: 0.6rem 0 0.3rem; }
  .prose :global(table) { border-collapse: collapse; font-size: 0.85rem; }
  .prose :global(td), .prose :global(th) { border: var(--line-width) solid var(--border); padding: 0.25rem 0.5rem; }
  .call {
    border-left: 3px solid var(--border);
    border-radius: 0 var(--radius) var(--radius) 0;
    background: var(--muted);
    font-family: "JetBrains Mono Variable", ui-monospace, monospace;
    font-size: 0.78rem;
    min-width: 0;
  }
  .tone-find { border-left-color: var(--chart-1); }
  .tone-grep { border-left-color: var(--chart-2); }
  .tone-glean { border-left-color: var(--chart-3); }
  .tone-graph { border-left-color: var(--chart-4); }
  .failed { border-left-color: var(--destructive); }
  .call-summary {
    display: flex;
    align-items: baseline;
    gap: 0.4rem;
    padding: 0.4rem 0.6rem;
    cursor: pointer;
    list-style: none;
  }
  .call-summary::-webkit-details-marker { display: none; }
  .dollar { color: var(--primary); }
  .call-cmd { flex: 1; min-width: 0; word-break: break-word; }
  .call-ms { color: var(--muted-foreground); font-size: 0.7rem; font-variant-numeric: tabular-nums; }
  .running {
    width: 0.5rem;
    height: 0.5rem;
    border-radius: 999px;
    background: var(--primary);
    animation: pulse 1s ease-in-out infinite;
  }
  .call-out {
    margin: 0;
    padding: 0.2rem 0.6rem 0.6rem;
    max-height: 18rem;
    overflow: auto;
    white-space: pre-wrap;
    word-break: break-word;
    color: var(--foreground);
    font: inherit;
  }
  .error { margin: 0; color: var(--destructive); font-size: 0.85rem; }
  .note { margin: 0; color: var(--muted-foreground); font-size: 0.72rem; }
  .thinking { display: inline-flex; gap: 0.3rem; padding: 0.4rem 0.2rem; }
  .thinking span {
    width: 0.4rem;
    height: 0.4rem;
    border-radius: 999px;
    background: var(--muted-foreground);
    animation: pulse 1.2s ease-in-out infinite;
  }
  .thinking span:nth-child(2) { animation-delay: 0.2s; }
  .thinking span:nth-child(3) { animation-delay: 0.4s; }
  @keyframes pulse { 0%, 100% { opacity: 0.3; } 50% { opacity: 1; } }
  .ran {
    margin: 0 1rem 0.5rem;
    padding: 0.4rem 0.6rem;
    border: 0;
    border-radius: var(--radius);
    background: var(--muted);
    color: var(--muted-foreground);
    font: inherit;
    font-size: 0.78rem;
    text-align: left;
    cursor: pointer;
  }
  .ran:hover { color: var(--foreground); }
  .ran:focus-visible { outline: var(--focus-width) solid var(--ring); outline-offset: var(--focus-offset); }
  .composer {
    display: flex;
    gap: 0.5rem;
    align-items: flex-end;
    padding: 0.75rem 1rem max(0.75rem, env(safe-area-inset-bottom, 0px));
    border-top: var(--line-width) solid var(--border);
  }
  .draft {
    flex: 1;
    min-width: 0;
    resize: none;
    padding: 0.55rem 0.7rem;
    border: var(--line-width) solid var(--input);
    border-radius: var(--radius);
    background: var(--raised);
    color: var(--foreground);
    font: inherit;
    font-size: 0.9rem;
    line-height: 1.4;
  }
  .send {
    padding: 0.55rem 0.9rem;
    border: 0;
    border-radius: var(--radius);
    background: var(--primary);
    color: var(--primary-foreground);
    font: inherit;
    font-size: 0.85rem;
    font-weight: 500;
    cursor: pointer;
  }
  .send:disabled { opacity: 0.5; cursor: default; }
  .chip:focus-visible, .send:focus-visible, .draft:focus-visible, .call-summary:focus-visible {
    outline: var(--focus-width) solid var(--ring);
    outline-offset: var(--focus-offset);
  }
  @media (prefers-reduced-motion: reduce) {
    .running, .thinking span { animation: none; opacity: 0.8; }
  }
</style>
