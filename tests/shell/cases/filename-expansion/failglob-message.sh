# tier: language
# world: seed
# stderr: exact
shopt -s failglob
echo *.nomatch 2>/dev/null
echo "status=$?"
