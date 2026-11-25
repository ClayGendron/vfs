# tier: language
# world: none
pair() {
  read -r a < "$1"
  read -r b < "$2"
  echo "a=[$a] b=[$b]"
}
pair <(echo left) <(echo right)
