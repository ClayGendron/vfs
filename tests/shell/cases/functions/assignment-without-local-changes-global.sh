# tier: language
# world: none
x=before
f() { x=after; y=new; }
f
echo "x=$x y=$y"
