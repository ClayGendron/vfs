# tier: language
# world: none
: > file.txt
[[ -e file.txt/ ]]; echo "file with slash: $?"
[[ -d ./ ]]; echo "dot slash: $?"
