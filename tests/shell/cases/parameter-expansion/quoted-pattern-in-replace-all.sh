# tier: language
# world: none
x='a.b.c'
p=.
echo "${x//"$p"/-} ${x//$p/-}"
