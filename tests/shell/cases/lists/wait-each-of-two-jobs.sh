# tier: language
# world: none
(exit 1) & p1=$!
(exit 2) & p2=$!
wait "$p1"; a=$?
wait "$p2"; b=$?
echo "first=$a second=$b"
