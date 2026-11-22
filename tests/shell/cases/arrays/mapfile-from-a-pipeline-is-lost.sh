# tier: language
# world: none
printf 'a\nb\n' | mapfile -t lines
echo "after pipe: count=${#lines[@]}"
mapfile -t lines < <(printf 'a\nb\n')
echo "after process substitution: count=${#lines[@]}"
