# tier: language
# world: none
kind() case $1 in
  [0-9]*) echo "$1 is a number" ;;
  *) echo "$1 is a word" ;;
esac
kind 42
kind abc
