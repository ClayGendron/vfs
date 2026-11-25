# tier: language
# world: none
false || (exit 2) || echo "third ran" || echo "fourth skipped"
echo "status=$?"
