# tier: language
# world: none
target=v
declare -n ref=target
plain=x
[[ -R ref ]]; echo "-R ref: $?"
[[ -R plain ]]; echo "-R plain: $?"
