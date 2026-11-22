# tier: language
# world: none
printf 'k=v\nk2=v2\n' > conf.txt
while IFS='=' read -r key val; do
  echo "key=$key val=$val"
done < conf.txt
