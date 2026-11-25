# tier: language
# world: none
a=0 b=0
echo $(( 1 ? (a = 5) : (b = 6) ))
echo "a=$a b=$b"
