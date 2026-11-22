# tier: language
# world: none
printf 'a\nb\n' > f
echo only >| f
mapfile -t lines < f
echo "lines=${#lines[@]} first=${lines[0]}"
