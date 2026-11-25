# tier: language
# world: none
echo hi > {a,b}
echo "status=$?"
[ -e a ] || [ -e b ] || echo "no file made"
