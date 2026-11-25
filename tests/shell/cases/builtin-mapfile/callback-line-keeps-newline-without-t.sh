# tier: language
# world: none
cb() { printf 'cb %s %q\n' "$1" "$2"; }
mapfile -c 1 -C cb arr <<< $'x\ny'
