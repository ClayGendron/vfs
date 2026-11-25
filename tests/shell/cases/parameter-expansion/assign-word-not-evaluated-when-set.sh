# tier: language
# world: none
x=set
: "${x:=$(echo side > marker)}"
[ -e marker ] && echo "evaluated" || echo "not evaluated"
