# tier: language
# world: none
x='a.b.c'
echo "${x//./-}"
y='a*b*c'
echo "${y//\*/+}"
echo "${y//"*"/+}"
echo "${y//*/+}"
