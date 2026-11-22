# tier: language
# world: none
f() { echo "in f: $x"; }
x=outer
x=temp f
echo "after: $x"
unset y
g() { echo "in g: $y"; }
y=only g
echo "after g: [${y-unset}]"
