# tier: language
# world: none
set -- a b c
x="$@"
echo "[$x]"
IFS=,
y=$@
z="$*"
echo "[$y] [$z]"
