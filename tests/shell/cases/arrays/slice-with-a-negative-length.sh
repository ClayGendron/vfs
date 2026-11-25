# tier: language
# world: none
a=(a b c d)
echo "[${a[@]:1:-1}]"
echo "status=$?"
