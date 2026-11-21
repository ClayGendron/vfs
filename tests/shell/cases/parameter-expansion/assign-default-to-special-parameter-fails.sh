# tier: language
# world: none
set --
( : "${@:=x}" ; echo "not reached" )
echo "status=$?"
