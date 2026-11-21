# tier: language
# world: none
echo "outer $(echo "inner $(echo "deep")")"
echo "$(echo 'single "dq" inside')"
x="$(printf '%s' "a  b")"
echo "[$x]"
