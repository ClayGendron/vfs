# tier: language
# world: none
[[ -t 0 ]]; echo "stdin is a terminal: $?"
[[ -t 1 ]] > out.txt; echo "stdout to a file is a terminal: $?"
