# tier: language
# world: none
s=abcdefgh
n=2
echo "${s:n:2} ${s:1+1:n*2} ${s: -3} ${s:(-3):2}"
