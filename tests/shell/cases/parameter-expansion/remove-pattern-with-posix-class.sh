# tier: language
# world: none
x='  hello'
echo "[${x##*[[:space:]]}]"
y=abc123
echo "[${y%%[[:digit:]]*}]"
