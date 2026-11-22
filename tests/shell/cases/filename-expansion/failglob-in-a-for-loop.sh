# tier: language
# world: seed
shopt -s failglob
for f in *.nomatch; do echo "loop $f"; done
echo "status=$?"
