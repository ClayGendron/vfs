# tier: language
# world: none
readonly x=1
unset x 2>&1
echo "status=$?"
