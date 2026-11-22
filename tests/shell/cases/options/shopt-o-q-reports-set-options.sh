# tier: language
# world: none
shopt -o -q errexit
echo "errexit=$?"
shopt -o -q noclobber
echo "noclobber before=$?"
set -C
shopt -o -q noclobber
echo "noclobber after=$?"
