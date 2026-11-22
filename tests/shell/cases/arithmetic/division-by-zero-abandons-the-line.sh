# tier: language
# world: none
echo before
echo $((1 / 0)); echo "same line"
echo "next line: $?"
