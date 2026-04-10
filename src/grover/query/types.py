"""Type aliases for ripgrep-compatible ``-t``/``--type`` filtering.

Maps language / file-type names (``python``, ``js``, ``rust``) to the set
of concrete file extensions that should match.  The canonical list is
sourced from ``rg --type-list`` and kept intentionally close to ripgrep's
defaults so that agents that already know ``rg -t python`` get the same
semantics from ``grover grep -t python``.

Resolution happens at the parser / CLI boundary — by the time values
reach the facade or the backend, they are concrete, lowercase extension
strings (no dot, no alias names).  An unknown alias is treated as a
literal extension, so ``-t py`` works without an entry and ``-t mjs``
falls through cleanly.
"""

from __future__ import annotations

TYPE_ALIASES: dict[str, tuple[str, ...]] = {
    # Shells
    "bash": ("sh", "bash", "zsh", "fish"),
    "sh": ("sh", "bash", "zsh", "fish"),
    "zsh": ("zsh",),
    "fish": ("fish",),
    # Systems languages
    "c": ("c", "h"),
    "cpp": ("cpp", "cc", "cxx", "hpp", "hh", "hxx", "h"),
    "cxx": ("cpp", "cc", "cxx", "hpp", "hh", "hxx", "h"),
    "cs": ("cs",),
    "csharp": ("cs",),
    "go": ("go",),
    "rust": ("rs",),
    "rs": ("rs",),
    "swift": ("swift",),
    "zig": ("zig",),
    # JVM
    "java": ("java",),
    "kotlin": ("kt", "kts"),
    "kt": ("kt", "kts"),
    "scala": ("scala", "sc"),
    "clojure": ("clj", "cljs", "cljc", "edn"),
    "groovy": ("groovy", "gvy", "gy", "gsh"),
    # Dynamic languages
    "py": ("py", "pyi"),
    "python": ("py", "pyi"),
    "rb": ("rb", "rbw"),
    "ruby": ("rb", "rbw"),
    "pl": ("pl", "pm", "t"),
    "perl": ("pl", "pm", "t"),
    "php": ("php", "phtml", "phps"),
    "lua": ("lua",),
    "r": ("r", "R"),
    "elixir": ("ex", "exs"),
    "erlang": ("erl", "hrl"),
    "haskell": ("hs", "lhs"),
    "ocaml": ("ml", "mli"),
    # Web / frontend
    "js": ("js", "mjs", "cjs"),
    "javascript": ("js", "mjs", "cjs"),
    "ts": ("ts", "tsx"),
    "typescript": ("ts", "tsx"),
    "jsx": ("jsx",),
    "tsx": ("tsx",),
    "html": ("html", "htm"),
    "css": ("css",),
    "scss": ("scss", "sass"),
    "sass": ("scss", "sass"),
    "less": ("less",),
    "vue": ("vue",),
    "svelte": ("svelte",),
    # Data / config
    "json": ("json",),
    "jsonc": ("jsonc",),
    "jsonl": ("jsonl", "ndjson"),
    "yaml": ("yaml", "yml"),
    "yml": ("yaml", "yml"),
    "toml": ("toml",),
    "ini": ("ini", "cfg"),
    "xml": ("xml",),
    "csv": ("csv",),
    "tsv": ("tsv",),
    # Docs
    "md": ("md", "markdown", "mdown", "mkdn"),
    "markdown": ("md", "markdown", "mdown", "mkdn"),
    "rst": ("rst",),
    "tex": ("tex", "ltx", "cls", "sty"),
    "org": ("org",),
    "txt": ("txt", "text"),
    # Databases
    "sql": ("sql",),
    # Infra / build
    "dockerfile": ("dockerfile",),
    "docker": ("dockerfile",),
    "make": ("mk", "mak", "makefile"),
    "makefile": ("mk", "mak", "makefile"),
    "cmake": ("cmake",),
    "terraform": ("tf", "tfvars"),
    "tf": ("tf", "tfvars"),
    "hcl": ("hcl", "tf", "tfvars"),
    "nix": ("nix",),
    "proto": ("proto",),
    "protobuf": ("proto",),
    "graphql": ("graphql", "gql"),
    "gql": ("graphql", "gql"),
    # Misc
    "log": ("log",),
    "diff": ("diff", "patch"),
    "patch": ("diff", "patch"),
}


def resolve_type_aliases(names: tuple[str, ...]) -> tuple[str, ...]:
    """Expand language/alias names to concrete extension tuples.

    >>> resolve_type_aliases(("python",))
    ('py', 'pyi')
    >>> resolve_type_aliases(("py", "pyi"))
    ('py', 'pyi')
    >>> resolve_type_aliases(("python", "js"))
    ('py', 'pyi', 'js', 'mjs', 'cjs')

    Unknown alias names are treated as literal extensions so that
    ``-t mjs`` works without an entry in the table and new extensions
    don't require updating Grover.  Duplicates are preserved in order
    of first appearance.
    """
    seen: set[str] = set()
    result: list[str] = []
    for name in names:
        key = name.lower()
        expansions = TYPE_ALIASES.get(key, (key,))
        for ext in expansions:
            ext_lower = ext.lower()
            if ext_lower not in seen:
                seen.add(ext_lower)
                result.append(ext_lower)
    return tuple(result)
