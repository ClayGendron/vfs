# tier: language
# world: none
set -u
unset x
echo "[${x:-ok}] [${x-ok2}] [${x+alt}]"
