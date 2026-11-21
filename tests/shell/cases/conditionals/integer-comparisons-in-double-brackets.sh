# tier: language
# world: none
a=7 b=12
[[ $a -eq $b ]]; echo "-eq: $?"
[[ $a -ne $b ]]; echo "-ne: $?"
[[ $a -lt $b ]]; echo "-lt: $?"
[[ $a -le 7 ]]; echo "-le: $?"
[[ $a -gt $b ]]; echo "-gt: $?"
[[ $b -ge 12 ]]; echo "-ge: $?"
