cd /Users/claygendron/Git/Repos/vfs/documentation
c() { echo "$1: $(grep -rlE "$2" --include='*.md' . | wc -l | tr -d ' ') pages"; }
c admonition '^(!!!|\?\?\?)'
c attr_list '\{[:.#][^}]*\}'
c def_list '^:   '
c footnotes '\[\^'
c raw_html '^<[a-z]'
c tables '^\|'
c snippets '--8<--'
c mermaid '^```mermaid'
c tabbed '^=== '
c mark '==[^= ][^=]*=='
c tasklist '^\s*[-*] \[[ x]\]'
c inlinehilite '`(#!|:::)'
c fence_options '^```[a-z]+ .*(hl_lines|linenums|title)='
c front_matter '^---$'
c blockquote '^> '
echo "fence languages:"; grep -rhoE '^```[a-zA-Z0-9_-]*' --include='*.md' . | sort | uniq -c
echo "images:"; grep -rnoE '!\[[^]]*\]\([^)]*\)' --include='*.md' . | cut -c1-140
echo "external links in pages:"; grep -rhoE '\]\(https?://[^)]*\)' --include='*.md' . | sort | uniq -c
echo "total pages: $(find . -name '*.md' | wc -l)"
