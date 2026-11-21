# tier: language
# world: none
f() { declare -x D=inner; declare -p D; }
f
echo "after f: [${D-unset}]"
