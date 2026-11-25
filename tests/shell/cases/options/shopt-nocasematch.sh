# tier: language
# world: none
[[ ABC == abc ]] && echo "match" || echo "no match"
shopt -s nocasematch
[[ ABC == abc ]] && echo "match" || echo "no match"
case HELLO in hello) echo "case match" ;; esac
