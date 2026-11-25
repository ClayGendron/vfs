# tier: language
# world: none
$(echo v=1) 2>/dev/null
echo "status=$? v=[${v-unset}]"
