# tier: language
# world: none
set -o errexit
shopt -o -q errexit && echo "errexit on"
false
echo "not reached"
