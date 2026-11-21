# tier: language
# world: none
: > plain.txt
[[ -L plain.txt ]]; echo "-L plain: $?"
[[ -h plain.txt ]]; echo "-h plain: $?"
[[ -L missing ]]; echo "-L missing: $?"
