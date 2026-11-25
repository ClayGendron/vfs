# tier: language
# world: none
x=hello
r='<&>'
echo "${x/l/$r}"
echo "${x/l/"$r"}"
