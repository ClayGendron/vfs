# tier: language
# world: none
set -e
{ false; echo "group continues"; } && echo "after group"
