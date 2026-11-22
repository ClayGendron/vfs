# tier: language
# world: none
shopt -s nocasematch
[[ HELLO == hello ]]; echo "== : $?"
[[ HeLLo == h*O ]]; echo "pattern: $?"
shopt -u nocasematch
[[ HELLO == hello ]]; echo "off again: $?"
