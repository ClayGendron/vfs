# tier: language
# world: none
IFS=:
v='a::b'
printf '[%s]\n' $v
v='a:::b'
set -- $v
echo "count=$#"
