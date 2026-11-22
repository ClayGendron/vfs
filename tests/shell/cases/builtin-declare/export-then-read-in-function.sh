# tier: language
# world: none
export G=from-top
f() { echo "in f: G=$G"; }
f
G=changed
f
