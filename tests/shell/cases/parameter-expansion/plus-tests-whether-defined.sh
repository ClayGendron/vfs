# tier: language
# world: none
unset x
[ -n "${x+set}" ] && echo "x set" || echo "x unset"
x=
[ -n "${x+set}" ] && echo "x set" || echo "x unset"
