# tier: language
# world: none
f() { local -; set -f; set -C; echo "inside: f=$([[ $- == *f* ]] && echo on || echo off) C=$([[ $- == *C* ]] && echo on || echo off)"; }
f
echo "after: f=$([[ $- == *f* ]] && echo on || echo off) C=$([[ $- == *C* ]] && echo on || echo off)"
