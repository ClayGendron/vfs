# tier: language
# world: none
v='a   b'
w=$v
echo "[$w]"
declare d=$v
echo "[$d]"
local_test() { local l=$v; echo "[$l]"; }
local_test
