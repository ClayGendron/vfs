# tier: language
# world: none
echo one >> log
echo two >> log
echo three >> log
mapfile -t lines < log
printf '%s|' "${lines[@]}"
echo
