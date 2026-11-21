# tier: language
# world: none
set -- a b c d
shift
echo "$# $1"
shift 2
echo "$# $1"
shift
echo "$# [${1-unset}]"
