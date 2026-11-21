# tier: language
# world: none
set -- 1 2 3
for x; do shift; echo "x=$x remaining=$#"; done
