# tier: language
# world: none
set -- a b c
IFS=,
x="$@"
y=$@
z="$*"
echo "[$x] [$y] [$z]"
