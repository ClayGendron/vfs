# tier: language
# world: none
(echo "in subshell"; exit 3; echo never)
echo "subshell status=$?"
