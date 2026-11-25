# tier: language
# world: none
: {fd}> f
: {fd}>&-
echo still-open >&$fd
echo "status=$?"
read -r x < f
echo "x=$x"
