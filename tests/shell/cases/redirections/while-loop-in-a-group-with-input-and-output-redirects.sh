# tier: language
# world: none
printf 'a\nb\n' > f
{ while read -r l; do echo "L:$l"; done; } < f > out.txt
mapfile -t lines < out.txt
printf '%s\n' "${lines[@]}"
