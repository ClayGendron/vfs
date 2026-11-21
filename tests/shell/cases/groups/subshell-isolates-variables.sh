# tier: language
# world: none
x=1
(x=2; y=3; echo "inside x=$x y=$y")
echo "outside x=$x y=${y-unset}"
