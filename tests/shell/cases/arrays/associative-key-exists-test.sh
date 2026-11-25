# tier: language
# world: none
declare -A m=([empty]="" [full]=x)
for k in empty full nothing; do
  if [[ -v m[$k] ]]; then echo "$k: exists"; else echo "$k: absent"; fi
done
