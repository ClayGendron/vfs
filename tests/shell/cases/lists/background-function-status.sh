# tier: language
# world: none
f() { return 9; }
f &
wait $!
echo "status=$?"
