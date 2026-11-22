# tier: language
# world: none
v=b
x=$(case $v in a) echo is-a;; b) echo is-b;; esac)
echo "[$x]"
