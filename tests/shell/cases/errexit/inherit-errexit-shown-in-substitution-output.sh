# tier: language
# world: none
shopt -s inherit_errexit
set -e
echo "[$(echo one; false; echo two)]"
echo "outer continues"
