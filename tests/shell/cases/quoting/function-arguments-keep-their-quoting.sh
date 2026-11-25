# tier: language
# world: none
f() { echo "count=$#"; printf '[%s]\n' "$@"; }
f 'a b' "c" d\ e '' "$(echo 'f  g')"
