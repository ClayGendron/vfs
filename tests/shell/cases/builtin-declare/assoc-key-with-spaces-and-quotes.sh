# tier: language
# world: none
declare -A m
k='a key'
m[$k]=1
m['b"q']=2
echo "spaced=${m[a key]} quoted=${m['b"q']}"
