# tier: language
# world: none
x=0
a() { local x=1; b; echo "a sees $x"; }
b() { local x=2; c; echo "b sees $x"; }
c() { echo "c sees $x"; x=3; }
a
echo "top sees $x"
