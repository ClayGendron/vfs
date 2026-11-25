# tier: language
# world: none
{ echo a; echo b; } | { read -r x; read -r y; echo "$y$x"; }
