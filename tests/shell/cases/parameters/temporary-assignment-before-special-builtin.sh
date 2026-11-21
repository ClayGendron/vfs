# tier: language
# world: none
x=1
x=2 :
echo "after colon: $x"
y=1
y=2 eval 'echo "inside eval: $y"'
echo "after eval: $y"
