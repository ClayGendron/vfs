# tier: language
# world: none
a=3 b=a
[[ b -eq 3 ]]; echo "b -> a -> 3: $?"
[ "$b" -eq 3 ] 2>/dev/null; echo "[ ] does not follow names: $?"
