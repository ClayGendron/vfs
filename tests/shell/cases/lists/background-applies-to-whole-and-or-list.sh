# tier: language
# world: none
false && echo "not printed" &
wait $!
echo "list status: $?"
