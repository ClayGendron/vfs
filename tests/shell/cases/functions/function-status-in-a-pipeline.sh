# tier: language
# world: none
f() { return 3; }
f | f
echo "status=$? pipestatus=${PIPESTATUS[*]}"
true | f
echo "last decides: $?"
