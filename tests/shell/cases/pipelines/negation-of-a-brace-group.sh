# tier: language
# world: none
! { true; false; }
echo "group negated: $?"
! (exit 3)
echo "subshell negated: $?"
