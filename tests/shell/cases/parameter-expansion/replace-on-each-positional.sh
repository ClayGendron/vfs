# tier: language
# world: none
set -- apple banana cherry
printf '[%s]\n' "${@/a/A}"
