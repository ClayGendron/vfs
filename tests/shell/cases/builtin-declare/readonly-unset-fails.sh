# tier: language
# world: none
readonly x=1
unset x 2>/dev/null
echo "status=$? x=$x"
