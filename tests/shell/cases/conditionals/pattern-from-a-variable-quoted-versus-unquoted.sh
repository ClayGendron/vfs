# tier: language
# world: none
pat='h*o'
[[ hello == $pat ]]; echo "unquoted var: $?"
[[ hello == "$pat" ]]; echo "quoted var: $?"
[[ 'h*o' == "$pat" ]]; echo "quoted var on literal: $?"
