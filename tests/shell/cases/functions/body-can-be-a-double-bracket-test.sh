# tier: language
# world: none
nonempty() [[ -n $1 ]]
nonempty x; echo "x -> $?"
nonempty ""; echo "empty -> $?"
