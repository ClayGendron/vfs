# tier: language
# world: none
empty=
for x in $empty; do echo "never"; done
echo "zero iterations, x=[${x-unset}]"
