# tier: language
# world: none
v='a b'
export E=$v
echo "[$E]"
f() { local L=$v M; echo "[$L] [${M-unset}]"; }
f
