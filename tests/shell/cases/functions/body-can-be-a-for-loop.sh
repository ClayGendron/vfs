# tier: language
# world: none
f() for w in "$@"; do echo "word=$w"; done
f a "b c" d
