# tier: language
# world: none
shopt -q extglob
echo "extglob before=$?"
shopt -s extglob
shopt -q extglob
echo "extglob after=$?"
shopt -q nullglob dotglob
echo "two unset=$?"
