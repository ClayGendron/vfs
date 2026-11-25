# tier: language
# world: none
outer() { echo "outer: $FUNCNAME"; inner; }
inner() { echo "inner: $FUNCNAME ${FUNCNAME[0]}"; }
outer
