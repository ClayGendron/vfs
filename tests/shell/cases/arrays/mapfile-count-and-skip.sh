# tier: language
# world: none
mapfile -t -s 1 -n 2 lines <<'END'
skip me
take one
take two
not taken
END
printf '[%s]\n' "${lines[@]}"
