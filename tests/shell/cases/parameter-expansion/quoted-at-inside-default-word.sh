# tier: language
# world: none
unset x
set -- "a b" c
printf '[%s]\n' "${x:-"$@"}"
