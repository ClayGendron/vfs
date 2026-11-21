# tier: language
# world: none
f() { echo out; echo err >&2; }
captured=$( { f 3>&1 1>&2 2>&3 3>&-; } 2>/dev/null )
echo "captured=[$captured]"
