# tier: language
# world: none
declare -A score=([ada]=36 [alan]=41)
echo "sum=$(( score[ada] + score[alan] ))"
(( score[ada] += 4 ))
echo "ada=${score[ada]}"
