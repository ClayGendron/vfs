# tier: language
# world: none
[[ ~ == "$HOME" ]] && echo "left expanded"
[[ $HOME/x == ~/x ]] && echo "right expanded"
