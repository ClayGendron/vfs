# tier: language
# world: none
shopt -s nocasematch
case HELLO in hello) echo "matched ignoring case" ;; esac
shopt -u nocasematch
case HELLO in hello) echo never ;; *) echo "case matters again" ;; esac
