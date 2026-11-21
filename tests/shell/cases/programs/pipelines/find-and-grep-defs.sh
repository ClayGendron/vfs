# tier: program
# world: seed
find . -name '*.py' | sort | while read -r f; do grep -H '^def ' "$f"; done
