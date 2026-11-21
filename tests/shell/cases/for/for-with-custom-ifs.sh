# tier: language
# world: none
v="a,b,,c"
IFS=,
for x in $v; do printf '[%s]\n' "$x"; done
