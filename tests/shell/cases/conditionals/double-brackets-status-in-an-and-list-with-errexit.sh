# tier: language
# world: none
set -e
[[ a == b ]] && echo "not printed"
echo "a false test in an and-list does not exit"
[[ a == b ]]
echo "not reached"
