# tier: language
# world: none
set -- a b c
IFS=,
x=$*
echo "[$x]"
