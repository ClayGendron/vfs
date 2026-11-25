# tier: language
# world: none
unset a
( : "${a[@]:=x}"; echo "not reached" )
echo "status=$?"
