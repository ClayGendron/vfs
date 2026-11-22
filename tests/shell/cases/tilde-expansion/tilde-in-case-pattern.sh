# tier: language
# world: none
case /home/agent in
  ~) echo "tilde pattern matched" ;;
  *) echo "no match" ;;
esac
