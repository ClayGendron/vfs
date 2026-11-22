# tier: language
# world: seed
echo hi > docs
echo "status=$?"
read -r x < docs
echo "read status=$?"
