# tier: language
# world: none
true | false | true
echo "first read: ${PIPESTATUS[*]}"
echo "second read: ${PIPESTATUS[*]}"
