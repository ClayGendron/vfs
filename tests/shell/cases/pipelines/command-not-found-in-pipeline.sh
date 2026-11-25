# tier: language
# world: none
nosuchcommand | true
echo "first stage missing: $? ${PIPESTATUS[*]}"
true | nosuchcommand
echo "last stage missing: $? ${PIPESTATUS[*]}"
