# tier: language
# world: none
echo a > one.log
echo b > two.log
echo new > *.log
echo "status=$?"
read -r x < one.log; echo "one=$x"
