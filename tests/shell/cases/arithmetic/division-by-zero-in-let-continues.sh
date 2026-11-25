# tier: language
# world: none
let 'x = 4 / 0'
echo "status: $? x=[${x-unset}]"
