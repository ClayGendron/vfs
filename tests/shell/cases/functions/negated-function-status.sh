# tier: language
# world: none
f() { return 0; }
! f
echo "negated=$?"
g() { return 5; }
! g
echo "negated=$?"
