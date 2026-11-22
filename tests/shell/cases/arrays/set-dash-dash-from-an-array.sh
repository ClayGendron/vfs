# tier: language
# world: none
a=("one two" three)
set -- "${a[@]}"
echo "argc=$# first=[$1]"
b=("$@")
echo "back to array: ${#b[@]}"
