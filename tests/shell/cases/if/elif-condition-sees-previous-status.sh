# tier: language
# world: none
if (exit 2); then :
elif echo "first elif saw $?"; false; then :
else echo "else saw $?"
fi
