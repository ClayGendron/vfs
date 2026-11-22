# tier: language
# world: none
unset x
printf '[%s]\n' "${x:-$'a\tb'}" ${x:-$'c\td'}
