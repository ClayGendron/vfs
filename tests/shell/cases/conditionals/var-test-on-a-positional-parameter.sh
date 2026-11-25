# tier: language
# world: none
set -- a b
[[ -v 1 ]]; echo "-v 1: $?"
[[ -v 3 ]]; echo "-v 3: $?"
