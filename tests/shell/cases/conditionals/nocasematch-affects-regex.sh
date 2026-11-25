# tier: language
# world: none
shopt -s nocasematch
[[ HELLO =~ ^hel ]]; echo "regex: $? [${BASH_REMATCH[0]}]"
