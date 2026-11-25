# tier: language
# world: none
x=$(false) && echo "not printed" || echo "assignment failed with $?"
y=$(true) && echo "assignment succeeded"
