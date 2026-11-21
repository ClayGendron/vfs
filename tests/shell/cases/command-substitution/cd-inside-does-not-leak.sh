# tier: language
# world: none
here=$PWD
d=$(cd / && pwd)
echo "inside=[$d]"
[ "$PWD" = "$here" ] && echo "outside unchanged"
