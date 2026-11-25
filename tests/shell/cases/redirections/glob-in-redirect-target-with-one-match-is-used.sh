# tier: language
# world: none
echo old > only.log
echo new > *.log
read -r x < only.log
echo "x=$x"
