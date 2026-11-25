# tier: language
# world: none
printf 'a\n\n\n' > f.txt
x=$(<f.txt)
echo "[$x] len=${#x}"
