# tier: language
# world: none
echo literal > *.nomatch
echo "status=$?"
read -r x < '*.nomatch'
echo "x=$x"
