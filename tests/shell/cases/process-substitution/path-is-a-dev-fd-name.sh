# tier: language
# world: none
f() { case $1 in /dev/fd/*) echo "dev fd path";; *) echo "other: $1";; esac; }
f <(true)
