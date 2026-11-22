# tier: language
# world: none
set -- a.txt b.txt c.log
printf '[%s]\n' "${@%.txt}"
