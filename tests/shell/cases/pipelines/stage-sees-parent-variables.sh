# tier: language
# world: none
greeting=hello
echo world | { read -r who; echo "$greeting $who"; }
