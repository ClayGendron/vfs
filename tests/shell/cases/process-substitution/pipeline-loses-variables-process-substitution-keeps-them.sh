# tier: language
# world: none
n=0
printf 'a\nb\n' | while read -r _; do n=$((n + 1)); done
echo "pipe n=$n"
n=0
while read -r _; do n=$((n + 1)); done < <(printf 'a\nb\n')
echo "procsub n=$n"
