# tier: language
# world: none
shopt -s inherit_errexit
set -e
echo start
x=$(false; echo after)
echo "not reached [$x]"
