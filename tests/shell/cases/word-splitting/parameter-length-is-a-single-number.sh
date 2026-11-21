# tier: language
# world: none
v='a b'
printf '[%s]\n' ${#v}
IFS=3
w=12345
printf '[%s]\n' ${#w} ${w}
