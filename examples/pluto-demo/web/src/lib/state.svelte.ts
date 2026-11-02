// Shared runes state: the workspace as the current principal sees it, and the one command log.
import { api, type LogEntry, type Principal, type State, type TreeNode } from "./api";

export type LogLine = LogEntry & { key: string; fresh: boolean };

export type AppId = "docs" | "sheets" | "slides" | "code" | "terminal";

export const APPS: { id: AppId; name: string }[] = [
  { id: "docs", name: "Docs" },
  { id: "sheets", name: "Sheets" },
  { id: "slides", name: "Slides" },
  { id: "code", name: "Code" },
  { id: "terminal", name: "Terminal" },
];

/** Which app a file opens in: slides decks, sheets for csv, code under /code, docs for the rest. */
export function appFor(path: string): AppId | null {
  if (path.startsWith("/slides/") && path.endsWith(".md")) return "slides";
  if (path.endsWith(".csv")) return "sheets";
  if (path.startsWith("/code/")) return "code";
  if (path.endsWith(".md")) return "docs";
  return null;
}

export type FileGroup = { folder: string; files: { name: string; path: string }[] };

/** The files an app lists, grouped by their folder, in tree order. */
export function filesFor(tree: TreeNode | null, app: AppId): FileGroup[] {
  const groups = new Map<string, FileGroup>();
  const walk = (node: TreeNode, folder: string) => {
    for (const child of node.children ?? []) {
      if (child.kind === "directory") walk(child, child.path);
      else if (appFor(child.path) === app) {
        const key = folder || "/";
        if (!groups.has(key)) groups.set(key, { folder: key, files: [] });
        groups.get(key)!.files.push({ name: child.name, path: child.path });
      }
    }
  };
  if (tree) walk(tree, "");
  return [...groups.values()];
}

class Workspace {
  principal = $state("");
  principals = $state<Principal[]>([]);
  embedder = $state<"model2vec" | "lexical">("lexical");
  tree = $state<TreeNode | null>(null);
  log = $state<LogLine[]>([]);
  openPath = $state<string | null>(null);
  app = $state<AppId>("docs");
  atlasOpen = $state(true);
  /** Commands Atlas ran while the person was in another app, cleared on visiting Terminal. */
  agentRuns = $state(0);
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
      const byAgent = entry.actor !== entry.principal;
      added.push({ ...entry, key, fresh: options.highlight === true && byAgent });
      if (byAgent && options.highlight && this.app !== "terminal") this.agentRuns += 1;
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

  openApp(app: AppId) {
    this.app = app;
    if (app === "terminal") this.agentRuns = 0;
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
