# tier: language
# world: none
x=1
unset x
echo "[${x-gone}]"
unset never_set
echo "unset of unknown: $?"
