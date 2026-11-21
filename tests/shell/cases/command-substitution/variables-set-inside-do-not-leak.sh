# tier: language
# world: none
x=before
y=$(x=inside; echo "$x")
echo "y=[$y] x=[$x]"
