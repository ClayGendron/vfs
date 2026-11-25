# tier: language
# world: none
[[ "hello world" =~ hello\ world ]]; echo "escaped space: $?"
re="o w"
[[ "hello world" =~ $re ]]; echo "variable: $? [${BASH_REMATCH[0]}]"
