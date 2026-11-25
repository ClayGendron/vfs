import type { HighlightedLine } from "#lib/highlighter";

/** A run of text inside a block, as the renderer draws it. */
export type Inline =
  | { type: "text"; text: string }
  | { type: "strong"; children: Inline[] }
  | { type: "em"; children: Inline[] }
  | { type: "code"; text: string }
  | { type: "link"; href: string; external: boolean; children: Inline[] }
  | { type: "break" }
  | { type: "svg"; markup: string };

/** One block of a page or of a docstring, as the renderer draws it. */
export type Block =
  | { type: "heading"; depth: number; id: string | null; children: Inline[] }
  | { type: "paragraph"; children: Inline[] }
  | { type: "plain"; children: Inline[] }
  | { type: "code"; text: string; lines: HighlightedLine[] | null }
  | { type: "table"; header: Inline[][]; rows: Inline[][][] }
  | { type: "list"; ordered: boolean; items: Block[][] }
  | { type: "quote"; children: Block[] }
  | { type: "rule" }
  | { type: "api"; object: ApiObject }
  | { type: "term"; term: GlossaryTerm };

/** One row under a glossary term: a name, the place it links to when it has one, and where that place is. */
export type TermRow = { name: string; href: string | null; where: string | null; code: boolean };

/** What stands under a glossary term's description: its types as the glossary file names them, then what the build found. */
export type GlossaryTerm = {
  /** The class or classes that are the term; empty when it has no class of its own. */
  types: TermRow[];
  /** Every class and function whose docstring marks the term. */
  code: TermRow[];
  /** Every page outside the reference section that links to the term. */
  documentation: TermRow[];
  /** The terms this description links to and the terms that link to it, in alphabetical order. */
  related: TermRow[];
};

/** What a name is, as the short word shown before it: a class, a method, an attribute, a function or a module. */
export type ApiSymbol = "class" | "meth" | "attr" | "func" | "mod";

/** One member of an exported name, ready to draw. */
export type ApiMember = {
  name: string;
  id: string;
  symbol: ApiSymbol;
  /** How it is declared: `async`, `property`, `classmethod` and the like. */
  labels: string[];
  code: HighlightedLine[] | null;
  doc: Block[];
  /** The fields of a class that a module lists and no page pulls in by name; empty for everything else. */
  members: ApiMember[];
};

/** One exported name, ready to draw: a second-level heading, then its members as third-level ones. */
export type ApiObject = {
  name: string;
  id: string;
  symbol: ApiSymbol;
  labels: string[];
  bases: string[];
  code: HighlightedLine[] | null;
  doc: Block[];
  members: ApiMember[];
};

/** One entry of a page's table of contents. An entry for an API name carries the word shown before it. */
export type TocEntry = { id: string; text: string; depth: 2 | 3; symbol?: ApiSymbol };

/** A page, ready to draw. Its description is its first paragraph, as a search result shows it. */
export type Page = { route: string; title: string; description: string; blocks: Block[]; toc: TocEntry[] };

/** A page as the navigation names it: the name its entry gives, or the page's own title. */
export type PageLink = { route: string; title: string };

export type NavGroup = { title: string | null; pages: PageLink[] };
export type NavTab = { title: string; href: string; groups: NavGroup[] };

/** One member of an exported name, as the Python script writes it. */
export type ExportedMember = {
  name: string;
  kind: string;
  labels: string[];
  signature: string | null;
  annotation: string | null;
  value: string | null;
  doc: string;
  members: ExportedMember[];
};

/** A class or function the glossary lists, as the Python script writes it: its page is null when it is on none. */
export type ExportedName = { name: string; id: string; page: string | null; public: boolean };

/** One glossary term, as the Python script writes it. */
export type ExportedTerm = {
  anchor: string;
  /** One sentence of plain text, for a link to the term to show; the glossary page does not print it. */
  summary: string;
  types: ExportedName[];
  code: ExportedName[];
  documentation: { page: string; title: string }[];
  related: string[];
};

/** The export the Python script writes, as the app reads it. */
export type ApiExport = {
  glossary: Record<string, ExportedTerm>;
  names: string[];
  objects: Record<
    string,
    {
      kind: string;
      labels: string[];
      signature: string | null;
      /** An exported type alias is an attribute: its value is the type it stands for. */
      annotation: string | null;
      value: string | null;
      bases: string[];
      doc: string;
      members: ExportedMember[];
    }
  >;
};
