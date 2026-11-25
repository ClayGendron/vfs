# tier: language
# world: none
e=""
[ -n $e ]; echo "-n \$e unquoted: $?"
[ -n "$e" ]; echo "-n \"\$e\" quoted: $?"
[ -z $e ]; echo "-z \$e unquoted: $?"
