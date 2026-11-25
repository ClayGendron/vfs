# tier: language
# world: none
make() { made() { echo "made with $1"; }; }
made 2>/dev/null; echo "before make: $?"
make
made x
