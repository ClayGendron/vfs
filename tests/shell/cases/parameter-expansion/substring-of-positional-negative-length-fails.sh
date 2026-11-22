# tier: language
# world: none
set -- a b c
( echo "${@:1:-1}"; echo "not reached" )
echo "status=$?"
