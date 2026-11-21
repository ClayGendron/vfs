# tier: language
# world: none
mapfile -d , arr < <(printf 'x,y,')
printf '%q\n' "${arr[@]}"
