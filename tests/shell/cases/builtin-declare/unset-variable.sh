# tier: language
# world: none
x=1
unset x
echo "x=[${x-gone}]"
unset x
echo "again status=$?"
