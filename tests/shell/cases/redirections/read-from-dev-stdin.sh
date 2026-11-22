# tier: language
# world: none
r=$(echo piped | { read -r x < /dev/stdin; echo "$x"; })
echo "r=[$r]"
