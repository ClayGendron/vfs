# tier: language
# world: none
# stderr: exact
read -z x <<< "hi"
echo "status=$?"
