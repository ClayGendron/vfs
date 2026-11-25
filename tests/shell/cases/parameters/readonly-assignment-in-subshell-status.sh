# tier: language
# world: none
readonly r=1
(r=2)
echo "subshell status=$?"
(r=2; echo "not reached")
echo "status=$?"
