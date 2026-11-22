# tier: language
# world: none
x=6
a=(x "x*2")
echo "$(( a[0] + 1 )) $(( a[1] ))"
