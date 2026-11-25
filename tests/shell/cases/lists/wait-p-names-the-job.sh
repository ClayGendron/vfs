# tier: language
# world: none
(exit 4) & p=$!
wait -p who "$p"
s=$?
[ "$who" = "$p" ] && echo "wait -p set the job's pid, status=$s"
