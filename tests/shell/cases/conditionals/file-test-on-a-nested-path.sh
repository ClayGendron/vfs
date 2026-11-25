# tier: language
# world: seed
[[ -f src/lib/helpers.py ]]; echo "nested file: $?"
[[ -d src/lib ]]; echo "nested dir: $?"
[[ -e src/lib/../util.py ]]; echo "through dot-dot: $?"
