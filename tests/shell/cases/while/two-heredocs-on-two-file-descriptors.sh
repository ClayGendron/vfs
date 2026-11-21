# tier: language
# world: none
while read -r a <&3 && read -r b <&4; do
  echo "$a-$b"
done 3<<'A' 4<<'B'
x
y
A
1
2
B
