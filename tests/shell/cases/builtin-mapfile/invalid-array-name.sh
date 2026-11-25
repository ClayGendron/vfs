# tier: language
# world: none
# stderr: exact
mapfile -t 1bad <<< "x"
echo "status=$?"
