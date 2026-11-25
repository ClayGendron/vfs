# tier: language
# world: none
f() { local r; printf -v r '%s!' "$1"; echo "inside=$r"; }
f hi
echo "outside=[${r-unset}]"
