# tier: language
# world: none
f() { set -f; }
f
case $- in *f*) echo "noglob still on";; *) echo "noglob off";; esac
set +f
