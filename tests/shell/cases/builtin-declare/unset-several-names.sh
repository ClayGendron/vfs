# tier: language
# world: none
a=1 b=2 c=3
unset a c
echo "a=[${a-unset}] b=$b c=[${c-unset}]"
