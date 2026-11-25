# tier: language
# world: none
a =1 2>/dev/null
echo "space before: $?"
a= 1 2>/dev/null
echo "space after: $?"
echo "a=[${a-unset}]"
