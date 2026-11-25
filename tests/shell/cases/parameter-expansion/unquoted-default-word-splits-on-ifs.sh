# tier: language
# world: none
IFS=:
unset x
printf '[%s]\n' ${x:-a:b}
