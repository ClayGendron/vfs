# tier: language
# world: none
echo "alpha beta" | while read -r first second; do
  echo "first=[$first] second=[$second]"
done
echo "status=$?"
