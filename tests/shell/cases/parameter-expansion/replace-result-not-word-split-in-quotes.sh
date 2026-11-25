# tier: language
# world: none
x=a-b-c
printf '[%s]\n' "${x//-/ }"
printf '[%s]\n' ${x//-/ }
