// Shared runes state: the workspace as the current principal sees it, and the one command log.
import { api, type LogEntry, type Principal, type State, type TreeNode } from "./api";

export type LogLine = LogEntry & { key: string; fresh: boolean };

class Workspace {
  principal = $state("");
  principals = $state<Principal[]>([]);
  embedder = $state<"model2vec" | "lexical">("lexical");
  tree = $state<TreeNode | null>(null);
  log = $state<LogLine[]>([]);
  openPath = $state<string | null>(null);
  shellOpen = $state(true);
  theme = $state<"light" | "dark">("light");
  loading = $state(true);
  error = $state<string | null>(null);

  get current(): Principal | undefined {
    return this.principals.find((p) => p.id === this.principal);
  }

  apply(state: State) {
    this.principal = state.principal;
    this.principals = state.principals;
    this.embedder = state.embedder;
    this.tree = state.tree;
    this.loading = false;
  }

  async refresh() {
    try {
      this.apply(await api.state());
      this.error = null;
    } catch (e) {
      this.error = e instanceof Error ? e.message : String(e);
      this.loading = false;
    }
  }

  async switchPrincipal(id: string) {
    if (id === this.principal) return;
    this.apply(await api.principal(id));
  }

  /** Merge server log entries, marking lines this client has not shown before. */
  mergeLog(entries: LogEntry[], options: { highlight?: boolean } = {}) {
    const seen = new Set(this.log.map((l) => l.key));
    const added: LogLine[] = [];
    for (const entry of entries) {
      const key = `${entry.ts}:${entry.actor}:${entry.command}`;
      if (seen.has(key)) continue;
      seen.add(key);
      added.push({
        ...entry,
        key,
        fresh: options.highlight === true && entry.actor !== entry.principal,
      });
    }
    if (added.length === 0) return;
    this.log = [...this.log, ...added].sort((a, b) => a.ts - b.ts);
    if (added.some((a) => a.fresh)) {
      setTimeout(() => {
        this.log = this.log.map((l) => (l.fresh ? { ...l, fresh: false } : l));
      }, 2400);
    }
  }

  async pollLog() {
    try {
      this.mergeLog(await api.log(), { highlight: true });
    } catch {
      // The server is restarting or away; the next poll will catch up.
    }
  }

  setTheme(theme: "light" | "dark") {
    this.theme = theme;
    const root = document.documentElement;
    root.classList.toggle("dark", theme === "dark");
    root.classList.toggle("light", theme === "light");
    try {
      localStorage.setItem("pluto-theme", theme);
    } catch {
      // Private window or blocked storage: the choice simply does not persist.
    }
  }

  initTheme() {
    let stored: string | null = null;
    try {
      stored = localStorage.getItem("pluto-theme");
    } catch {
      stored = null;
    }
    if (stored === "dark" || stored === "light") {
      this.theme = stored;
    } else {
      this.theme = window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
    }
  }
}

export const workspace = new Workspace();
