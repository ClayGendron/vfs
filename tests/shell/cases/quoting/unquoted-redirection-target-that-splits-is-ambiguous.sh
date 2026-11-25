# tier: language
# world: none
f='two words'
echo hi > $f
echo "status=$?"
[ -e two ] || echo "no file named two"
