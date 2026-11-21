# tier: language
# world: none
for ((i = 0; i < 100000; i++)); do :; done &
disown
echo "disown status=$?"
jobs
echo "jobs after disown: none"
