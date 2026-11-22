# tier: program
# world: seed
grep -rl alpha . | sort | while read -r f; do echo "match: $f"; done
