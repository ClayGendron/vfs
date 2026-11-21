# tier: language
# world: none
arr=(src/a.c src/b.c lib/c.c)
printf '[%s]\n' "${arr[@]#*/}"
