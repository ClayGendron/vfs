# tier: language
# world: none
mapfile -t lines <<'END'
alpha
beta gamma
END
printf '[%s]\n' "${lines[@]}"
