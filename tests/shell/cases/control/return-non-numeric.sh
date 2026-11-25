# tier: language
# world: none
f() { return abc; }
f 2>/dev/null
echo "status=$?"
