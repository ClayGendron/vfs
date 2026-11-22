# tier: language
# world: none
nums=(4 11 7 20 3)
big=()
for n in "${nums[@]}"; do (( n > 5 )) && big+=("$n"); done
echo "big=${big[*]} count=${#big[@]}"
