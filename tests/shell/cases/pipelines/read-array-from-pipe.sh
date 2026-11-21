# tier: language
# world: none
echo "x y z" | { read -r -a parts; echo "n=${#parts[@]} last=${parts[2]}"; }
