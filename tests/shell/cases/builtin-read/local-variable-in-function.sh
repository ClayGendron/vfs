# tier: language
# world: none
f() { local v; read -r v <<< "inner"; echo "in=[$v]"; }
f
echo "out=[${v-unset}]"
