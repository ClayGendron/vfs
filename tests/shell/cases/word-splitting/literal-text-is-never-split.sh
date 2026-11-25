# tier: language
# world: none
IFS=:
v=x:y
printf '[%s]\n' a:b $v "c:d"
