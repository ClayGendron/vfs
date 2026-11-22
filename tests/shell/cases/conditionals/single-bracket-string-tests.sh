# tier: language
# world: none
x=hello
[ "$x" = hello ]; echo "= : $?"
[ "$x" == hello ]; echo "== : $?"
[ "$x" != hello ]; echo "!= : $?"
[ -n "$x" ]; echo "-n: $?"
[ -z "$x" ]; echo "-z: $?"
