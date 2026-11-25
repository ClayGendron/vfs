# tier: language
# world: none
set -u
set --
echo "count=$# at=[$@] star=[$*]"
for a in "$@"; do echo "never $a"; done
echo "ok"
