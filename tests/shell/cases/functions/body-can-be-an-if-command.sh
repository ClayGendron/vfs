# tier: language
# world: none
f() if [ "$1" = yes ]; then echo "said yes"; else echo "said $1"; fi
f yes
f no
