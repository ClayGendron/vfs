# tier: language
# world: none
IFS=$' \v'
v=$'a\v\vb'
set -- $v
echo "count=$#"
