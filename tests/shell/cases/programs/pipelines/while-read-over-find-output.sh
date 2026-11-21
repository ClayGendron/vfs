# tier: program
# world: seed
find docs -type f | sort | while read -r f; do printf '%s:%s\n' "${f##*/}" "$(head -n 1 "$f")"; done
