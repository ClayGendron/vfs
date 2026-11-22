# tier: language
# world: none
op='>'
echo hi $op out.txt
read -r x < out.txt 2>/dev/null
echo "read status=$?"
