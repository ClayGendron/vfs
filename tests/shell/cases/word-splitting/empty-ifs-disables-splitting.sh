# tier: language
# world: none
IFS=
v='a b	c'
printf '[%s]\n' $v
set -- $v
echo "count=$#"
