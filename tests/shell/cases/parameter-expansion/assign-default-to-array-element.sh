# tier: language
# world: none
unset a
: "${a[2]:=z}"
echo "a2=${a[2]} count=${#a[@]} keys=${!a[*]}"
