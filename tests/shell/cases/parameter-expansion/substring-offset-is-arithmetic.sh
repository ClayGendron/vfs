# tier: language
# world: none
x=abcdefgh
i=1 n=2
echo "${x:i+1:n*2}"
echo "${x:$i:$n}"
