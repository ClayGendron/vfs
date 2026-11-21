# tier: language
# world: none
set -- a b
shift x 2>/dev/null
echo "status=$? count=$#"
