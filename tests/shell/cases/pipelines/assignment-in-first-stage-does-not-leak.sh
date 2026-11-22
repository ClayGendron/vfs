# tier: language
# world: none
x=0
{ x=1; echo "first stage x=$x"; } | { read -r msg; echo "got: $msg"; }
echo "parent x=$x"
