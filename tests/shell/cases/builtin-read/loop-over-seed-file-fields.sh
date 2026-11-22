# tier: language
# world: seed
IFS=, read -r header < data/people.csv
echo "header=[$header]"
while IFS=, read -r name age city; do
  [ "$name" = name ] && continue
  echo "$name is $age"
done < data/people.csv
