# tier: language
# world: none
# stderr: exact
unset x
: "${x?unset}"
echo "not reached"
