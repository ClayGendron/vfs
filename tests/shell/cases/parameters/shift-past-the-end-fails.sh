# tier: language
# world: none
set -- a b
shift 3
echo "status=$? count=$#"
shift 0
echo "shift 0: $? count=$#"
set --
shift
echo "empty shift: $?"
