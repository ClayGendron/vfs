import type {
  GrammarState,
  HighlighterCore,
  ThemeRegistrationRaw,
  ThemedToken,
} from "shiki/core";

/**
 * Shiki with the JavaScript engine and one hand-made theme whose every colour
 * is a code token, `var(--code-<slot>)`. A token renders as a class, never a
 * `style`: `tokenClass` maps the slot to its `text-code-<slot>` utility.
 *
 * `highlightCode` is the one-shot form for a server `load`, so a prerendered
 * page ships no Shiki. `loadHighlighter` is the incremental form the
 * `useHighlightedCode` hook streams through. Shiki itself is imported lazily,
 * so a page that only renders highlighted lines it was given loads none of it.
 */

/** The theme's name, as Shiki registers it. */
const THEME = "pluto-code";

const slot = (name: string) => `var(--code-${name})`;

/** One theme rule: these scope families take this slot, bold or underlined when said. */
function rule(scope: string[], name: string, fontStyle?: "bold" | "underline") {
  return {
    scope,
    settings: fontStyle
      ? { foreground: slot(name), fontStyle }
      : { foreground: slot(name) },
  };
}

/**
 * The palette as a theme, by role. Every colour is a code
 * slot, and every slot is a role that holds in any language: a type name, a
 * key, a decorator. A deeper selector beats a shallower one, which is how a
 * role escapes its parent's rule (the `f` of an f-string escapes `storage`).
 * Operators, brackets and plain names stay in the body; a definition is also
 * told by weight. Shiki and CodeMirror then colour the same code the same way.
 */
export const codeTheme: ThemeRegistrationRaw = {
  name: THEME,
  type: "light",
  colors: {
    "editor.foreground": slot("foreground"),
    "editor.background": slot("background"),
  },
  settings: [
    // Comments, docstrings and their quotes, quotes in Markdown, diff headers.
    rule(
      [
        "comment",
        "punctuation.definition.comment",
        "string.quoted.docstring",
        "string.quoted.docstring punctuation.definition.string",
        "markup.quote",
        "meta.diff.header",
        "meta.diff.index",
      ],
      "comment",
    ),
    // Strings, their own quotes (a literal reads as one thing), regexps, inline code, link titles, the f-string prefix.
    rule(
      [
        "string",
        "string punctuation.definition.string",
        "string.regexp",
        "markup.inline.raw",
        "string.other.link.title",
        "storage.type.string.python",
        "entity.name.tag.doctype",
      ],
      "string",
    ),
    // Escapes, format placeholders, interpolation marks, JSX braces, entities.
    rule(
      [
        "constant.character.escape",
        "constant.character.format.placeholder",
        "constant.other.placeholder",
        "storage.type.format",
        "punctuation.section.embedded",
        "punctuation.definition.template-expression",
        "punctuation.definition.interpolation",
        "constant.character.entity",
      ],
      "escape",
    ),
    // Numbers, units, colours, dates.
    rule(
      [
        "constant.numeric",
        "keyword.other.unit",
        "constant.other.color",
        "constant.other.time",
        "constant.other.date",
      ],
      "number",
    ),
    // Language constants, named constants, enum members, symbols.
    rule(
      [
        "constant.language",
        "variable.other.constant",
        "variable.other.enummember",
        "constant.other.symbol",
        "support.constant",
      ],
      "constant",
    ),
    // A CSS value word (`flex`, `monospace`) is not a constant: the body.
    rule(
      ["support.constant.property-value", "support.constant.font-name"],
      "foreground",
    ),
    // Keywords, storage words, word operators, directives, Markdown marks.
    rule(
      [
        "keyword",
        "storage",
        "keyword.control",
        "keyword.other",
        "keyword.operator.expression",
        "keyword.operator.new",
        "keyword.operator.delete",
        "keyword.operator.logical.python",
        "keyword.operator.sizeof",
        "keyword.operator.cast",
        "keyword.control.directive",
        "punctuation.section.embedded.begin.php",
        "meta.diff.range",
        "punctuation.definition.heading",
        "punctuation.definition.list.begin.markdown",
      ],
      "keyword",
    ),
    // Symbol operators are the body's: both editors leave them there.
    rule(["keyword.operator", "storage.type.function.arrow"], "foreground"),
    // Functions: calls, methods, macros, preprocessor functions.
    rule(
      [
        "entity.name.function",
        // The called name alone: `meta.function-call` would take the whole
        // call, arguments included, in the Python grammar.
        "meta.function-call.generic",
        "support.function.macro",
        "entity.name.function.macro",
        "entity.name.function.preprocessor",
      ],
      "function",
    ),
    // A definition is also told by weight.
    rule(
      [
        "meta.function entity.name.function",
        "meta.function.definition entity.name.function",
        "meta.method.declaration entity.name.function",
        "entity.name.function.definition",
      ],
      "function",
      "bold",
    ),
    // Built-in functions, kernel functions, magic names, CSS functions.
    rule(
      ["support.function", "support.variable.magic", "support.variable"],
      "builtin",
    ),
    // Types: classes, interfaces, namespaces, primitives, lifetimes.
    rule(
      [
        "entity.name.type",
        "entity.name.class",
        "entity.name.namespace",
        "entity.name.scope-resolution",
        "entity.other.inherited-class",
        "support.type",
        "support.class",
        "entity.name.package",
        "storage.type.primitive",
        "storage.type.built-in",
        "support.type.primitive",
        "keyword.type",
        "storage.type.numeric",
        "storage.type.string",
        "storage.type.boolean",
        "storage.type.byte",
        "storage.type.rune",
        "storage.type.error",
        "storage.type.uintptr",
        "storage.type.sql",
        "storage.type.java",
        "storage.type.cs",
        "storage.type.kotlin",
        "storage.type.swift",
        "storage.type.php",
        "entity.name.lifetime",
        "storage.modifier.lifetime",
      ],
      "type",
    ),
    // Tags, selectors, components, TOML tables.
    rule(
      [
        "entity.name.tag",
        "entity.other.attribute-name.class.css",
        "entity.other.attribute-name.id.css",
        "entity.other.attribute-name.pseudo-class.css",
        "entity.other.attribute-name.pseudo-element.css",
        "support.class.component",
        "entity.name.section.toml",
      ],
      "tag",
    ),
    // The angle brackets around a tag are punctuation: the body.
    rule(["punctuation.definition.tag"], "foreground"),
    // Keys, attributes, fields, object members, shell and PHP variables.
    rule(
      [
        "entity.other.attribute-name",
        "support.type.property-name",
        "meta.object-literal.key",
        "meta.attribute.python",
        "variable.other.property",
        "variable.object.property",
        "variable.other.object",
        "variable.other.member",
        "variable.other.readwrite.instance",
        "entity.name.variable.field",
        "entity.name.tag.yaml",
        "variable.other.key.toml",
        "variable.other.normal",
        "variable.other.positional",
        "variable.other.special",
        "variable.other.for",
        "variable.other.php",
        "variable.css",
        // The shell's `$*`, `$@`, `$?`: special parameters, not a self.
        "variable.language.special",
      ],
      "property",
    ),
    // Decorators, annotations, attributes.
    rule(
      [
        "meta.decorator",
        "entity.name.function.decorator",
        "punctuation.definition.decorator",
        "meta.attribute.rust",
        "storage.type.annotation",
        "meta.attribute.cs",
        "meta.attribute.php",
        "storage.modifier.attribute",
        "meta.annotation",
      ],
      "decorator",
    ),
    // self, cls, this, super, $0. Python's `self` is
    // `variable.parameter.function.language.special.self` in a parameter
    // list and `variable.language.special.self` in a body; both are named so
    // they win over the shell's `variable.language.special` above.
    rule(
      [
        "variable.language",
        "variable.language.special.self",
        "variable.parameter.function.language.special.self",
      ],
      "self",
    ),
    // Links, underlined.
    rule(
      ["markup.underline.link", "string.other.link.destination"],
      "link",
      "underline",
    ),
    rule(["invalid", "invalid.illegal", "invalid.deprecated"], "invalid"),
    rule(["markup.inserted"], "inserted"),
    rule(["markup.deleted"], "deleted"),
    rule(["markup.changed"], "changed"),
    // Headings and bold text: weight, no colour.
    rule(
      ["markup.heading", "entity.name.section.markdown", "markup.bold"],
      "foreground",
      "bold",
    ),
    // Plain names, parameters (keyword arguments included), punctuation, brackets: the body.
    rule(
      ["variable", "variable.parameter", "punctuation", "meta.brace"],
      "foreground",
    ),
  ],
};

/**
 * The slot-to-class table: every slot but `foreground`, written out so Tailwind's scanner sees each class.
 * A token in the `foreground` slot carries no class: the `pre` is already
 * `text-foreground`.
 */
export const tokenClasses: Record<string, string> = {
  [slot("background")]: "text-code-background",
  [slot("comment")]: "text-code-comment",
  [slot("keyword")]: "text-code-keyword",
  [slot("constant")]: "text-code-constant",
  [slot("string")]: "text-code-string",
  [slot("number")]: "text-code-number",
  [slot("escape")]: "text-code-escape",
  [slot("function")]: "text-code-function",
  [slot("builtin")]: "text-code-builtin",
  [slot("type")]: "text-code-type",
  [slot("tag")]: "text-code-tag",
  [slot("property")]: "text-code-property",
  [slot("decorator")]: "text-code-decorator",
  [slot("self")]: "text-code-self",
  [slot("link")]: "text-code-link",
  [slot("invalid")]: "text-code-invalid",
  [slot("inserted")]: "text-code-inserted",
  [slot("deleted")]: "text-code-deleted",
  [slot("changed")]: "text-code-changed",
  [slot("active-line")]: "text-code-active-line",
};

/** Shiki's `fontStyle` is a bit field: italic 1, bold 2, underline 4. */
const BOLD = 2;
const UNDERLINE = 4;

/** The class a token renders with: its slot's utility, `font-medium` for bold, `underline` for underline. Empty for a foreground token. */
export function tokenClass(
  token: Pick<ThemedToken, "color" | "fontStyle">,
): string {
  const classes: string[] = [];
  const colour = token.color ? tokenClasses[token.color] : undefined;
  if (colour) classes.push(colour);
  const bits = token.fontStyle ?? 0;
  if (bits > 0 && (bits & BOLD) !== 0) classes.push("font-medium");
  if (bits > 0 && (bits & UNDERLINE) !== 0) classes.push("underline");
  return classes.join(" ");
}

// The twenty-six languages. Each one loads the first time it is used; the list costs nothing until a block names a language. Add the
// languages you need beside them.
const languages = {
  bash: () => import("shiki/langs/shellscript.mjs"),
  c: () => import("shiki/langs/c.mjs"),
  cpp: () => import("shiki/langs/cpp.mjs"),
  csharp: () => import("shiki/langs/csharp.mjs"),
  css: () => import("shiki/langs/css.mjs"),
  diff: () => import("shiki/langs/diff.mjs"),
  docker: () => import("shiki/langs/docker.mjs"),
  go: () => import("shiki/langs/go.mjs"),
  html: () => import("shiki/langs/html.mjs"),
  java: () => import("shiki/langs/java.mjs"),
  javascript: () => import("shiki/langs/javascript.mjs"),
  json: () => import("shiki/langs/json.mjs"),
  jsx: () => import("shiki/langs/jsx.mjs"),
  kotlin: () => import("shiki/langs/kotlin.mjs"),
  markdown: () => import("shiki/langs/markdown.mjs"),
  php: () => import("shiki/langs/php.mjs"),
  python: () => import("shiki/langs/python.mjs"),
  ruby: () => import("shiki/langs/ruby.mjs"),
  rust: () => import("shiki/langs/rust.mjs"),
  sql: () => import("shiki/langs/sql.mjs"),
  svelte: () => import("shiki/langs/svelte.mjs"),
  swift: () => import("shiki/langs/swift.mjs"),
  toml: () => import("shiki/langs/toml.mjs"),
  tsx: () => import("shiki/langs/tsx.mjs"),
  typescript: () => import("shiki/langs/typescript.mjs"),
  yaml: () => import("shiki/langs/yaml.mjs"),
};

const aliases: Record<string, keyof typeof languages> = {
  "c#": "csharp",
  "c++": "cpp",
  cjs: "javascript",
  cs: "csharp",
  cts: "typescript",
  dockerfile: "docker",
  js: "javascript",
  kt: "kotlin",
  kts: "kotlin",
  md: "markdown",
  mjs: "javascript",
  mts: "typescript",
  py: "python",
  rb: "ruby",
  rs: "rust",
  sh: "bash",
  shell: "bash",
  shellscript: "bash",
  ts: "typescript",
  yml: "yaml",
  zsh: "bash",
};

let highlighter: Promise<HighlighterCore> | undefined;

/** Core and the JavaScript engine, loaded once, on first use. */
async function getHighlighter() {
  highlighter ??= (async () => {
    const [{ createHighlighterCore }, { createJavaScriptRegexEngine }] =
      await Promise.all([
        import("shiki/core"),
        import("shiki/engine/javascript"),
      ]);
    return createHighlighterCore({
      themes: [codeTheme],
      langs: [],
      // Strict: all twenty-six grammars compile under it.
      engine: createJavaScriptRegexEngine({ forgiving: false }),
    });
  })();
  return highlighter;
}

function getLanguage(language: string) {
  const name = language.toLowerCase();
  if (name in languages) return name as keyof typeof languages;
  return aliases[name] ?? null;
}

/** One highlighted token. Render it as a `<span>` with this class. */
export type HighlightedToken = {
  content: string;
  /** The token's classes, or "" for a token in the foreground slot. */
  class: string;
};

/** A line of plain text, or the highlighted tokens of a line. */
export type HighlightedLine = string | HighlightedToken[];

function toHighlightedLine(tokens: ThemedToken[]): HighlightedToken[] {
  return tokens.map((token) => ({
    content: token.content,
    class: tokenClass(token),
  }));
}

export type Highlighter = NonNullable<
  Awaited<ReturnType<typeof loadHighlighter>>
>;

/**
 * Loads a language and returns a highlighter for it, or null for a language
 * that is not listed. A null highlighter costs nothing: Shiki is not loaded.
 */
export async function loadHighlighter(language: string) {
  const lang = getLanguage(language);
  if (!lang) return null;

  const shiki = await getHighlighter();
  if (!shiki.getLoadedLanguages().includes(lang)) {
    await shiki.loadLanguage(languages[lang]);
  }

  return {
    /**
     * Returns the tokens of each line, and the grammar state after the last
     * line. Pass that state back to continue where the code left off.
     */
    highlight(code: string, state?: GrammarState) {
      const result = shiki.codeToTokens(code, {
        lang,
        theme: THEME,
        grammarState: state,
      });
      return {
        lines: result.tokens.map((line) => toHighlightedLine(line)),
        state: shiki.getLastGrammarState(result.tokens),
      };
    },
  };
}

/** Returns the tokens of each line, or null for a language that is not listed. For a server `load`. */
export async function highlightCode(code: string, language: string) {
  const loaded = await loadHighlighter(language);
  return loaded ? loaded.highlight(code).lines : null;
}
