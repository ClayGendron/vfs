# tier: language
# world: none
set -- a b
shift -1 2>/dev/null
echo "status=$? count=$#"
