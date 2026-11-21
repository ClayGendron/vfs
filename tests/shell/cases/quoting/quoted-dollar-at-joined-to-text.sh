# tier: language
# world: none
set -- a 'b c'
printf '[%s]\n' "<$@>"
printf '[%s]\n' "<$*>"
