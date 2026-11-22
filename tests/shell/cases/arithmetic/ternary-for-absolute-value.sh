# tier: language
# world: none
for n in -7 7 0; do echo $(( n < 0 ? -n : n )); done
