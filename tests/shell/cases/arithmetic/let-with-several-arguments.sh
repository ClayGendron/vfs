# tier: language
# world: none
let a=1 b=a+1 c=b*10
echo "a=$a b=$b c=$c"
let 1 0
echo "last zero: $?"
let 0 1
echo "last one: $?"
