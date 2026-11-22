# tier: language
# world: none
s=
for w in a b c; do
  s="${s:+$s,}$w"
done
echo "$s"
