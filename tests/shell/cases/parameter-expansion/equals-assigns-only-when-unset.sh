# tier: language
# world: none
x=
: "${x=filled}"
echo "empty stays=[$x]"
unset x
: "${x=filled}"
echo "unset gets=[$x]"
