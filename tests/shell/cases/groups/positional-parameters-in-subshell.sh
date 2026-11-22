# tier: language
# world: none
set -- a b
(set -- x y z; echo "inside: $# $*")
echo "outside: $# $*"
