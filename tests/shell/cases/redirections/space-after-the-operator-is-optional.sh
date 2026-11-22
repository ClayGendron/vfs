# tier: language
# world: none
echo tight>t1
echo spaced > t2
echo apart >   t3
read -r a < t1; read -r b < t2; read -r c < t3
echo "$a $b $c"
