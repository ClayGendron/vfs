# tier: language
# world: none
mapfile -t arr < <(printf 'a\r\nb\r\n')
printf '%q\n' "${arr[@]}"
