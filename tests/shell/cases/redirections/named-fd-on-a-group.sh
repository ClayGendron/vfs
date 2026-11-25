# tier: language
# world: none
{ echo grouped >&$out; } {out}> g.txt
read -r x < g.txt
echo "x=$x"
