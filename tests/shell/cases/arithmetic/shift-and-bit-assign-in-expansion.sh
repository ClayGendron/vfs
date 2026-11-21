# tier: language
# world: none
x=1
echo "$((x <<= 3)) $((x |= 3)) $((x &= 6)) $((x ^= 1)) $((x >>= 1))"
