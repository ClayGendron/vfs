# tier: language
# world: none
f() { return 7; }
echo | f
echo "status=$?"
f | true
echo "status=$? first=${PIPESTATUS[0]}"
