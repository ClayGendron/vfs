# tier: language
# world: none
eval 'echo from-eval' > e.txt
read -r x < e.txt
echo "x=$x"
cmd='echo inside-string > inner.txt'
eval "$cmd"
read -r y < inner.txt
echo "y=$y"
