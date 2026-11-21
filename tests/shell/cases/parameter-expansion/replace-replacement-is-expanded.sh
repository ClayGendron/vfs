# tier: language
# world: none
x=hello
n=3
echo "${x/l/$((n+1))}"
echo "${x/o/$(echo !)}"
