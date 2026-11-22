# tier: language
# world: none
if true; then echo yes; else echo no; fi > if.txt
read -r x < if.txt
echo "x=$x"
