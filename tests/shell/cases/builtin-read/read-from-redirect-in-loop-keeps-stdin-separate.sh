# tier: language
# world: none
printf '1\n2\n' > nums.txt
while read -r n <&3; do
  echo "n=$n"
done 3< nums.txt
