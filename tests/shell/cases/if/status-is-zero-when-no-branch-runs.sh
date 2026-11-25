# tier: language
# world: none
if false; then echo "not printed"; fi
echo "no branch: $?"
if false; then :; elif (exit 3); then :; fi
echo "no branch after failing elif: $?"
