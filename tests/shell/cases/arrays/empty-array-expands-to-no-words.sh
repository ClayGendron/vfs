# tier: language
# world: none
e=()
printf 'count of words: %s\n' $#
set -- "${e[@]}"
echo "args from empty array: $#"
set -- "${e[*]}"
echo "args from quoted star: $#"
