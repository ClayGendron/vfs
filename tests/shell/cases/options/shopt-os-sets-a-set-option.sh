# tier: language
# world: none
shopt -o -s noglob
[[ -o noglob ]] && echo "noglob on"
shopt -o -u noglob
[[ -o noglob ]] || echo "noglob off"
