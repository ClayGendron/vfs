# tier: language
# world: none
n=0
printf '%s\n' a b c | while read -r l; do n=$((n + 1)); echo "inside n=$n"; done
echo "outside n=$n"
