# tier: language
# world: none
set -u
set -- one
echo "first=$1"
echo "second=$2" 2>/dev/null
echo "not reached"
