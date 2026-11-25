# tier: language
# world: none
set -- a b c
printf '[%s]\n' "x$@y"
set -- one
printf '[%s]\n' "x$@y"
