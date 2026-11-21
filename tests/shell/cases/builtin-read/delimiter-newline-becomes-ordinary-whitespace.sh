# tier: language
# world: none
read -d . a b <<< $'x\ny.z'
echo "a=[$a] b=[$b]"
IFS= read -r -d . c <<< $'p\nq.r'
printf 'c=%q\n' "$c"
