# tier: language
# world: seed
shopt -s globstar
for f in **; do [ "$f" = .hidden ] && echo "hidden found"; done
shopt -s dotglob
for f in **; do [ "$f" = .hidden ] && echo "hidden found with dotglob"; done
echo "done"
