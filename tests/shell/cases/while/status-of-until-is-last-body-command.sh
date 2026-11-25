# tier: language
# world: none
n=0
until ((n == 2)); do ((n++)); (exit 4); done
echo "status=$?"
