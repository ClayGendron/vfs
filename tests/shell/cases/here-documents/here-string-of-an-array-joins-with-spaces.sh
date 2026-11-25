# tier: language
# world: none
arr=(one "two words" three)
read -r -a back <<< "${arr[@]}"
echo "count=${#back[@]}"
IFS= read -r line <<< "${arr[*]}"
echo "line=[$line]"
