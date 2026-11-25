# tier: language
# world: none
set -- 'a b' '' c
for w in "$@"; do echo "[$w]"; done
echo ---
for w in $@; do echo "[$w]"; done
