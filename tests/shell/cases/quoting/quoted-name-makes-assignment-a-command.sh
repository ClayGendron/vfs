# tier: language
# world: none
'x=1' 2>/dev/null
echo "quoted whole: $?"
"x"=1 2>/dev/null
echo "quoted name: $?"
echo "x=[${x-unset}]"
x="1"
echo "quoted value: x=$x"
