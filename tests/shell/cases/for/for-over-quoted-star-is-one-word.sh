# tier: language
# world: none
set -- "a b" c
for x in "$*"; do printf '[%s]\n' "$x"; done
