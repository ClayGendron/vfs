# tier: language
# world: none
shopt -s inherit_errexit
set -e
echo "before"
x=$(false; echo after)
echo "not reached"
