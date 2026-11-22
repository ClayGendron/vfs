# tier: language
# world: none
! echo negated > n.txt
echo "status=$?"
read -r x < n.txt
echo "x=$x"
