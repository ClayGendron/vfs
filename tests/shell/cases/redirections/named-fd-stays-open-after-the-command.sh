# tier: language
# world: none
: {fd}> f
echo "through named fd" >&$fd
: {fd}>&-
read -r x < f
echo "x=$x"
