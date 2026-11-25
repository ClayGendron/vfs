# tier: language
# world: none
{ echo via-four >&4; echo via-three >&3; } 3> f 4>&3-
echo "status=$?"
mapfile -t lines < f
printf '[%s]\n' "${lines[@]}"
