# tier: language
# world: none
x=$(set -e; echo one; false; echo two)
echo "x=[$x] status=$?"
