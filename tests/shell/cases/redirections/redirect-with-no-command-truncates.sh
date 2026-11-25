# tier: language
# world: none
printf 'a\nb\n' > f
> f
mapfile -t lines < f
echo "lines=${#lines[@]}"
