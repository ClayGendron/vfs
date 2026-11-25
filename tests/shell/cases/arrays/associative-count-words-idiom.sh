# tier: language
# world: none
declare -A seen
for w in pear apple fig apple pear apple; do
  (( seen[$w]++ ))
done
echo "apple=${seen[apple]} pear=${seen[pear]} fig=${seen[fig]} distinct=${#seen[@]}"
