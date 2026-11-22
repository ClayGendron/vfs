# tier: language
# world: none
set -e
( false; echo "inner" ) || echo "outer"
echo "continued"
