# tier: language
# world: none
x=1
x=2 true
echo "after true: $x"
unset y
y=3 read -r z <<< 'zz'
echo "y=[${y-unset}] z=$z"
