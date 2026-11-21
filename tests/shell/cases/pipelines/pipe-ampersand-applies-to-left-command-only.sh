# tier: language
# world: none
{ echo left-err >&2; } |& { read -r l; echo "piped:$l"; echo right-err >&2; } 2>/dev/null
