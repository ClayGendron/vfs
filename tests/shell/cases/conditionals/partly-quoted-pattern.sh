# tier: language
# world: none
[[ abc == "a"* ]]; echo "\"a\"*: $?"
[[ 'a*c' == "a*"c ]]; echo "\"a*\"c on a*c: $?"
[[ abc == "a*"c ]]; echo "\"a*\"c on abc: $?"
