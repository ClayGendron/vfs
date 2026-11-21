# tier: language
# world: none
> empty.out
echo "status=$?"
mapfile -t lines < empty.out
echo "lines=${#lines[@]}"
