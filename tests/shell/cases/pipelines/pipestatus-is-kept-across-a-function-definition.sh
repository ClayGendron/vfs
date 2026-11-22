# tier: language
# world: none
true | false
f() { :; }
echo "after a definition: ${PIPESTATUS[*]}"
false | true
for i in; do :; done
echo "after an empty loop: ${PIPESTATUS[*]}"
