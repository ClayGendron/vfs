# tier: language
# world: none
for ((i = 0; i < 300000; i++)); do :; done &
jobs
wait
echo "waited status=$?"
