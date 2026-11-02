// The typed client for the demo server's /api contract (see ../../API.md).

export type Kind = "directory" | "file";

export type TreeNode = {
  name: string;
  path: string;
  kind: Kind;
  children?: TreeNode[];
};

export type Principal = {
  id: string;
  name: string;
  role: string;
  kind: "user" | "service";
};

export type State = {
  principal: string;
  principals: Principal[];
  embedder: "model2vec" | "lexical";
  tree: TreeNode;
};

export type ShellResponse = {
  ts: number;
  command: string;
  principal: string;
  actor: string;
  verb: string;
  ok: boolean;
  output: string;
  elapsed_ms: number;
  paths: string[];
};

export type LogEntry = {
  ts: number;
  principal: string;
  actor: string;
  command: string;
  verb: string;
  ok: boolean;
  elapsed_ms: number;
  output?: string;
};

export type FileBody = { path: string; content: string; kind: Kind };

export type ChatTurn = { role: "user" | "assistant"; content: string };

export type ChatEvent =
  | { event: "text"; data: { delta: string } }
  | { event: "tool"; data: { id: string; command: string } }
  | {
      event: "result";
      data: { id: string; output: string; ok: boolean; verb: string; elapsed_ms: number };
    }
  | { event: "done"; data: { mode: "live" | "scripted" } }
  | { event: "error"; data: { message: string } };

async function json<T>(input: string, init?: RequestInit): Promise<T> {
  const response = await fetch(input, {
    ...init,
    headers: { "content-type": "application/json", ...(init?.headers ?? {}) },
  });
  if (!response.ok) {
    throw new Error(`${init?.method ?? "GET"} ${input} failed with ${response.status}`);
  }
  return (await response.json()) as T;
}

export const api = {
  state: () => json<State>("/api/state"),
  principal: (id: string) =>
    json<State>("/api/principal", { method: "POST", body: JSON.stringify({ id }) }),
  shell: (command: string) =>
    json<ShellResponse>("/api/shell", { method: "POST", body: JSON.stringify({ command }) }),
  log: () => json<LogEntry[]>("/api/log"),
  file: (path: string) => json<FileBody>(`/api/file?path=${encodeURIComponent(path)}`),
  save: (path: string, content: string) =>
    json<{ ok: boolean; output: string }>("/api/file", {
      method: "PUT",
      body: JSON.stringify({ path, content }),
    }),

  /** POST /api/chat and yield each server-sent event as it arrives. */
  async *chat(message: string, history: ChatTurn[]): AsyncGenerator<ChatEvent> {
    const response = await fetch("/api/chat", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ message, history }),
    });
    if (!response.ok || !response.body) {
      throw new Error(`The agent is not answering (status ${response.status}).`);
    }
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    for (;;) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      let boundary = buffer.indexOf("\n\n");
      while (boundary !== -1) {
        const block = buffer.slice(0, boundary);
        buffer = buffer.slice(boundary + 2);
        const parsed = parseBlock(block);
        if (parsed) yield parsed;
        boundary = buffer.indexOf("\n\n");
      }
    }
    const tail = parseBlock(buffer);
    if (tail) yield tail;
  },
};

function parseBlock(block: string): ChatEvent | null {
  let event = "message";
  const data: string[] = [];
  for (const line of block.split("\n")) {
    if (line.startsWith("event:")) event = line.slice(6).trim();
    else if (line.startsWith("data:")) data.push(line.slice(5).trimStart());
  }
  if (data.length === 0) return null;
  try {
    return { event, data: JSON.parse(data.join("\n")) } as ChatEvent;
  } catch {
    return null;
  }
}

/** The mark colour a verb's output carries: find blue, grep red, glean amber, graph green. */
export function verbTone(verb: string): "find" | "grep" | "glean" | "graph" | "plain" {
  switch (verb) {
    case "ls":
    case "tree":
    case "find":
    case "glob":
      return "find";
    case "grep":
      return "grep";
    case "glean":
      return "glean";
    case "graph":
      return "graph";
    default:
      return "plain";
  }
}

export function verbOf(command: string): string {
  return command.trim().split(/\s+/)[0] ?? "";
}
