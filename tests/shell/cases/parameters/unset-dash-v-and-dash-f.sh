# tier: language
# world: none
g=var
g() { echo "function g"; }
unset -f g
echo "var still: $g"
g 2>/dev/null
echo "function gone: $?"
unset -v g
echo "[${g-unset}]"
