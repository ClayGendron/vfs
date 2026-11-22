# tier: language
# world: none
false || false && echo "x" || echo "y"
echo "status=$?"
true || false && false
echo "status=$?"
