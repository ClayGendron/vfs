# tier: language
# world: seed
for f in *; do [ "$f" = .hidden ] && echo "hidden matched"; done
echo "done"
