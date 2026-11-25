# tier: language
# world: none
x=set
echo "${x:-$(echo side > marker)}"
[ -e marker ] && echo "evaluated" || echo "not evaluated"
