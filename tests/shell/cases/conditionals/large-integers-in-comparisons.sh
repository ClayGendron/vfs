# tier: language
# world: none
[[ 9223372036854775807 -gt 0 ]]; echo "max -gt 0: $?"
[ 9223372036854775807 -gt 9223372036854775806 ]; echo "[ max -gt max-1 ]: $?"
