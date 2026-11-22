# tier: language
# world: none
f() { case $1 in pre/dev/fd/*) echo "joined";; *) echo "[$1]";; esac; }
f pre<(true)
