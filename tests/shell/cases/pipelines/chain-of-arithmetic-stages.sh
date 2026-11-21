# tier: language
# world: none
echo 5 | { read -r n; echo $((n * 2)); } | { read -r n; echo $((n + 1)); }
