# tier: language
# world: none
set=value
echo "[${set:-$(echo ran > ran.txt)}]"
[ -e ran.txt ] && echo "ran" || echo "not ran"
unset set
echo "[${set:-$(echo ran > ran.txt; echo dflt)}]"
[ -e ran.txt ] && echo "ran" || echo "not ran"
