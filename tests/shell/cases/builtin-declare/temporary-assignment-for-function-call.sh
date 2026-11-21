# tier: language
# world: none
f() { echo "in f: V=$V"; }
V=temporary f
echo "after: [${V-unset}]"
