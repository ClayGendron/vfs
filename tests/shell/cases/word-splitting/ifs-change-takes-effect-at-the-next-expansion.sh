# tier: language
# world: none
v='a:b c'
IFS=: ; printf '[%s]\n' $v
unset IFS; printf '[%s]\n' $v
