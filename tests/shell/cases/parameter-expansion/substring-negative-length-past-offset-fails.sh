# tier: language
# world: none
x=abcdef
( echo "${x:4:-3}" ; echo "not reached" )
echo "status=$?"
