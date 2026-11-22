# tier: language
# world: none
re='^a+$'
[[ aaa =~ $re ]]; echo "unquoted: $?"
[[ aaa =~ "$re" ]]; echo "quoted: $?"
[[ '^a+$' =~ "$re" ]]; echo "quoted on itself: $?"
