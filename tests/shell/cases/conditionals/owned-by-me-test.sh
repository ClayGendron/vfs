# tier: language
# world: none
: > mine.txt
[[ -O mine.txt ]]; echo "-O: $?"
[[ -G mine.txt ]]; echo "-G: $?"
[[ -O missing.txt ]]; echo "-O missing: $?"
