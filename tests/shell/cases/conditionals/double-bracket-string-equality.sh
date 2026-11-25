# tier: language
# world: none
x=hello
[[ $x == hello ]]; echo "== hello: $?"
[[ $x == world ]]; echo "== world: $?"
[[ $x = hello ]]; echo "single = : $?"
