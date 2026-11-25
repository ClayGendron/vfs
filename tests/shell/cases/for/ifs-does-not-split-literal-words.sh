# tier: language
# world: none
IFS=,
for x in a,b c; do printf '[%s]\n' "$x"; done
