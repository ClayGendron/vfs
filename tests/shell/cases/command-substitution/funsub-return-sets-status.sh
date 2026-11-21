# tier: language
# world: none
y=${ echo out; return 3; echo never; }
echo "y=[$y] status=$?"
