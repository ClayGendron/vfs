# tier: language
# world: none
f() { local x=1; if [ "$x" = 1 ]; then echo yes; fi; for i in a b; do echo $i; done; }
declare -f f
