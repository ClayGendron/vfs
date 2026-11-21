# tier: language
# world: none
case $- in *f*) echo "f before" ;; *) echo "no f before" ;; esac
set -f
case $- in *f*) echo "f after" ;; esac
set -u
case $- in *u*) echo "u after" ;; esac
