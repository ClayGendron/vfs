# tier: language
# world: none
! [[ a == b ]]; echo "outside: $?"
[[ ! a == b ]]; echo "inside: $?"
! [[ a == a ]] || echo "outside negation of true is false"
