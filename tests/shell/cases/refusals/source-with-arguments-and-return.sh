# tier: language
# world: none
printf '%s\n' 'echo "args: $*"' 'return 3' 'echo "not reached"' >script.sh
source ./script.sh one two
echo "status=$?"
