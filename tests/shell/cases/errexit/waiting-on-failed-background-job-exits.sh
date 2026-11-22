# tier: language
# world: none
set -e
false &
wait $!
echo "not reached"
