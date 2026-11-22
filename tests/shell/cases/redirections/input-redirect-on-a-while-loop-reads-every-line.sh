# tier: language
# world: none
printf 'one\ntwo\nthree\n' > in.txt
n=0
while IFS= read -r line; do
  n=$((n + 1))
  echo "$n:$line"
done < in.txt
echo "after loop n=$n"
