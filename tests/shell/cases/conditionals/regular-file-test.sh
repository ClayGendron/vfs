# tier: language
# world: none
: > file.txt
[[ -f file.txt ]]; echo "-f file: $?"
[[ -f . ]]; echo "-f dot: $?"
[[ -f nothing ]]; echo "-f missing: $?"
