# tier: language
# world: none
set -- a 'b c' ''
for x; do printf '[%s]\n' "$x"; done
