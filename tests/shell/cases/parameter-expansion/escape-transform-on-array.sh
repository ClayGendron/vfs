# tier: language
# world: none
arr=('1\t2' '3\\4')
printf '[%s]\n' "${arr[@]@E}"
