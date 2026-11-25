# tier: language
# world: none
cmd='printf %s-'
$cmd a b
echo
"$cmd" a 2>/dev/null
echo "quoted command name: $?"
