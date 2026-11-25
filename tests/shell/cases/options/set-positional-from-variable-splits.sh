# tier: language
# world: none
v='one two  three'
set -- $v
echo "count=$#"
set -- "$v"
echo "quoted count=$#"
