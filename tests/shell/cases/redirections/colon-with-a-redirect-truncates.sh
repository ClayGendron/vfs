# tier: language
# world: none
printf 'x\ny\nz\n' > f
: > f
mapfile -t lines < f
echo "lines=${#lines[@]}"
