# tier: language
# world: none
declare -A m
m["*"]=star
m["a=b"]=equals
m['$x']=dollar
echo "star=${m["*"]} equals=${m[a=b]} dollar=${m['$x']} count=${#m[@]}"
