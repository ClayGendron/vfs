# tier: language
# world: none
[ "$(echo x)" = x ] && echo "single bracket"
[[ $(echo 'a b') == "a b" ]] && echo "double bracket"
