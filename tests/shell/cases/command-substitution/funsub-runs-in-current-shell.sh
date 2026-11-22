# tier: language
# world: none
x=before
y=${ x=inside; echo "got $x"; }
echo "y=[$y] x=[$x]"
