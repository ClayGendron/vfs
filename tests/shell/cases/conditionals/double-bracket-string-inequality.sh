# tier: language
# world: none
x=hello
[[ $x != world ]]; echo "!= world: $?"
[[ $x != hello ]]; echo "!= hello: $?"
