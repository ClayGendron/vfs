# tier: language
# world: none
printf 'first\nsecond\n' > f.txt
x=$(<f.txt)
echo "[$x]"
