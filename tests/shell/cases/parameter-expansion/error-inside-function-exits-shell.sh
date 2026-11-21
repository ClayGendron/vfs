# tier: language
# world: none
unset x
f() { : "${x:?gone}"; echo "in f after"; }
f
echo "not reached"
