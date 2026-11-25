# tier: language
# world: none
FUNCNEST=3
down() { echo "depth $1"; down $(( $1 + 1 )); }
down 1
echo "status=$?"
