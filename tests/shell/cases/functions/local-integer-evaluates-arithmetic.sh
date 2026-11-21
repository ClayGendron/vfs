# tier: language
# world: none
f() { local -i n=3+4; echo "n=$n"; n+=1; echo "n=$n"; n="2*5"; echo "n=$n"; }
f
