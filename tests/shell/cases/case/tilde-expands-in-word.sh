# tier: language
# world: none
case ~ in /home/agent) echo "word tilde expanded" ;; *) echo "other" ;; esac
case /home/agent in ~) echo "pattern tilde expanded" ;; esac
