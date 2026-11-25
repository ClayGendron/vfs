# tier: language
# world: none
e=""
s="text"
[[ -z $e ]]; echo "-z empty: $?"
[[ -z $s ]]; echo "-z text: $?"
[[ -n $s ]]; echo "-n text: $?"
[[ -n $e ]]; echo "-n empty: $?"
[[ -z $nothing_here ]]; echo "-z unset: $?"
