# tier: language
# world: none
echo one > f
set -o noclobber
echo two >> f
echo "status=$?"
mapfile -t lines < f
printf '[%s]\n' "${lines[@]}"
