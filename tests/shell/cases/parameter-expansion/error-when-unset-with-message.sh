# tier: language
# world: none
# stderr: exact
unset x
echo "before"
: "${x:?is required}"
echo "not reached"
