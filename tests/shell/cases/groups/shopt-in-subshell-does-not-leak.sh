# tier: language
# world: none
(shopt -s nocasematch; [[ A == a ]] && echo "inside: nocasematch on")
[[ A == a ]] || echo "outside: nocasematch off"
