# tier: language
# world: none
x=outer
f() ( x=inner; echo "inside x=$x" )
f
echo "after x=$x"
