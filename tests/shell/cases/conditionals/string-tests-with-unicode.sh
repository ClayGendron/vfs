# tier: language
# world: none
s="héllo"
[[ $s == h?llo ]]; echo "? matches one character: $?"
[[ ${#s} -eq 5 ]]; echo "length 5: $?"
[[ é < z ]]; echo "é < z: $?"
