# tier: language
# world: none
name="two words"
echo hi > $name
echo "status=$?"
read -r x < "two words"
echo "read status=$?"
