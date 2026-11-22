# tier: language
# world: none
set -e
false && true || false && echo "not printed"
echo "continued status=$?"
