# tier: language
# world: none
set -- a b c
shift $#
echo "status=$? count=$#"
shift
echo "empty shift status=$?"
