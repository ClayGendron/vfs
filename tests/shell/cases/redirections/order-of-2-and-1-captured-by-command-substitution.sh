# tier: language
# world: none
f() { echo out; echo err >&2; }
a=$(f 2>&1 >/dev/null)
b=$(f >/dev/null 2>&1)
c=$(f 2>&1)
echo "a=[$a]"
echo "b=[$b]"
echo "c=[${c//$'\n'/,}]"
