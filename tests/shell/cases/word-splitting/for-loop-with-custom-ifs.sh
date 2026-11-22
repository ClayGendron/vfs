# tier: language
# world: none
IFS=,
csv='red,green,,blue'
for c in $csv; do echo "[$c]"; done
