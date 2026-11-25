# tier: language
# world: none
count=0
while read -r _; do (( count++ )); done < <(printf 'a\nb\nc\n')
echo "count=$count"
