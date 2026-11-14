import { marked } from "marked";
const samples: Record<string, string> = {
  admonition: '!!! note "Title"\n    Body of the note.\n',
  details: '??? tip\n    Hidden body.\n',
  footnote: "A claim.[^1]\n\n[^1]: The source.\n",
  def_list: "Term\n:   Its definition.\n",
  tabbed: '=== "Python"\n\n    ```python\n    x = 1\n    ```\n',
  mark: "This is ==marked== text.\n",
  attr_list: "[Get Started](get-started.md){ .md-button }\n",
  tasklist: "- [x] done\n- [ ] not done\n",
  mermaid: "```mermaid\ngraph LR; A-->B;\n```\n",
  snippets: '--8<-- "file.md"\n',
  inlinehilite: "`#!python range(3)`\n",
  strikethrough: "~~gone~~\n",
  raw_html: "<details><summary>More</summary>\n\nBody\n\n</details>\n",
  fence_options: '```python title="a.py" hl_lines="1"\nx = 1\n```\n',
};
const kinds = (tokens: any[]): string[] => tokens.flatMap((t) => [t.type + (t.type === "code" ? `(${t.codeBlockStyle ?? "fenced"},lang=${JSON.stringify(t.lang)})` : ""), ...(t.tokens ? kinds(t.tokens) : []), ...(t.items ? kinds(t.items) : [])]);
for (const [name, text] of Object.entries(samples)) console.log(`${name}: ${kinds(marked.lexer(text)).join(" ")}`);
