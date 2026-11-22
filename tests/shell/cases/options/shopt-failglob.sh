# tier: language
# world: none
# world: seed
shopt -s failglob
echo *.txt
echo *.none 2>/dev/null
echo "status=$?"
