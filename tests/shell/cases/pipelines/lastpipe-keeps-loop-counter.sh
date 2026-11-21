# tier: language
# world: none
shopt -s lastpipe
n=0
printf '%s\n' a b c | while read -r l; do n=$((n + 1)); done
echo "n=$n"
