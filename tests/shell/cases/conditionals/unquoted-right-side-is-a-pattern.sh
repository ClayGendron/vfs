# tier: language
# world: none
f=report.txt
[[ $f == *.txt ]]; echo "*.txt: $?"
[[ $f == r?port.* ]]; echo "r?port.*: $?"
[[ $f == [a-r]* ]]; echo "[a-r]*: $?"
[[ $f == *.md ]]; echo "*.md: $?"
