# tier: language
# world: none
f=report.txt
[[ $f == "*.txt" ]]; echo "quoted *.txt: $?"
s='*.txt'
[[ $s == "*.txt" ]]; echo "literal star: $?"
