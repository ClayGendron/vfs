# tier: language
# world: none
set -u
e=()
echo "empty expansion ok: [${e[@]}] count=${#e[@]}"
a=(x)
echo "a1=[${a[1]-default}]"
( echo "${a[1]}" ) 2>/dev/null
echo "unbound element status=$?"
