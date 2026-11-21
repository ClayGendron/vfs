# tier: language
# world: none
a=(a b c)
if (( ${#a[@]} > 2 )); then echo "more than two"; fi
[[ ${#a[@]} -eq 3 ]] && echo "exactly three"
