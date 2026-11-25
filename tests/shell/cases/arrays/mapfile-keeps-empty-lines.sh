# tier: language
# world: none
mapfile -t lines <<'END'
one

three

END
echo "count=${#lines[@]}"
printf '[%s]\n' "${lines[@]}"
