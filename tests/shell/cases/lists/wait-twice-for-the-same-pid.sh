# tier: language
# world: none
(exit 6) & p=$!
wait "$p"
echo "first wait: $?"
wait "$p"
echo "second wait: $?"
