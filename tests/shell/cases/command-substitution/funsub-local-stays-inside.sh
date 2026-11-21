# tier: language
# world: none
x=outer
y=${ local x=inner; echo "$x"; }
echo "y=[$y] x=[$x]"
