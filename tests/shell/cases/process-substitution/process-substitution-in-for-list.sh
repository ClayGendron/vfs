# tier: language
# world: none
for f in <(true) <(true); do
  case $f in /dev/fd/*) echo "fd path";; esac
done
