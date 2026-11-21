# tier: language
# world: none
f=report.txt
if [[ $f == *.txt ]]; then echo "glob match"; fi
if [[ $f == "*.txt" ]]; then echo "wrong"; else echo "quoted pattern is literal"; fi
