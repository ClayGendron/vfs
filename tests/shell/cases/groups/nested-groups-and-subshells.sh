# tier: language
# world: none
x=0
{ x=1; (x=2; { x=3; echo "deepest x=$x"; }; echo "subshell x=$x"); echo "group x=$x"; }
echo "top x=$x"
