# tier: language
# world: none
flags=$(( 1 | 4 ))
(( flags & 4 )) && echo "has 4"
(( flags & 2 )) || echo "lacks 2"
(( flags |= 2, flags &= ~1 ))
echo "flags=$flags"
