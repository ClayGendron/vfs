# tier: language
# world: none
e=
[ -n $e ] && echo "unquoted -n is true"
[ -n "$e" ] || echo "quoted -n is false"
[ -z $e ] && echo "unquoted -z is true"
