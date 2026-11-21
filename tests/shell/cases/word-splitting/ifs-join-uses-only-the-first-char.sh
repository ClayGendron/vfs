# tier: language
# world: none
set -- a b c
IFS='-+'
echo "$*"
v='x+y-z'
printf '[%s]\n' $v
