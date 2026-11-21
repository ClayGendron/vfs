# tier: language
# world: none
declare -A m
m["first key"]=a
k="second key"
m[$k]=b
m['third key']=c
echo "[${m[first key]}] [${m["second key"]}] [${m[$k]}] [${m['third key']}]"
echo "count=${#m[@]}"
