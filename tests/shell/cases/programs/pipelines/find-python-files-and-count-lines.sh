# tier: program
# world: seed
find src -name '*.py' | sort | while IFS= read -r f; do printf '%s %s\n' "$(wc -l < "$f")" "$f"; done
