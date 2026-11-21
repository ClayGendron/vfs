# tier: language
# world: none
[ b > a ]
echo "status=$?"
[ -e a ] && echo "a file named a was created"
[ b \> a ]; echo "escaped b > a: $?"
[ a \> b ]; echo "escaped a > b: $?"
