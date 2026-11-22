# tier: language
# world: none
e=()
printf '[%s]\n' "x${e[@]}y"
set -- "${e[@]}"
echo "alone: $#"
