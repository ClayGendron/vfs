# tier: language
# world: none
echo "a:b:c" | { IFS=: read -r x y z; echo "$z$y$x"; }
