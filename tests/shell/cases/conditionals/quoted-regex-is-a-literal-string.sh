# tier: language
# world: none
[[ "a.c" =~ "a.c" ]]; echo "quoted on a.c: $?"
[[ "abc" =~ "a.c" ]]; echo "quoted on abc: $?"
[[ "abc" =~ a.c ]]; echo "unquoted on abc: $?"
