# tier: language
# world: none
set --
echo "before"
( : "${1:=x}" ; echo "not reached" )
echo "status=$?"
