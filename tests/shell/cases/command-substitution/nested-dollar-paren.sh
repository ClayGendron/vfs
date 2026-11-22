# tier: language
# world: none
x=$(echo "outer $(echo "inner $(echo deepest)")")
echo "[$x]"
