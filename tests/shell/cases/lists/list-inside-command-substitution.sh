# tier: language
# world: none
v=$(false || echo fallback)
echo "v=$v"
w=$(true && echo first; echo second)
echo "w=[$w]"
