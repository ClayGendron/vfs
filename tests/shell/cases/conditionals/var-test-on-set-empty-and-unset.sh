# tier: language
# world: none
set_var=value
empty_var=""
unset gone
[[ -v set_var ]]; echo "set: $?"
[[ -v empty_var ]]; echo "empty: $?"
[[ -v gone ]]; echo "unset: $?"
