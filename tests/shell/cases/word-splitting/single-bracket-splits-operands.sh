# tier: language
# world: none
v='a b'
[ $v = 'a b' ] 2>/dev/null
echo "unquoted: $?"
[ "$v" = 'a b' ]
echo "quoted: $?"
