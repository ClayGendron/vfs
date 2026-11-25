# tier: language
# world: none
v=b
case $v in
  a) echo "was a" ;;
  b) echo "was b" ;;
esac > case.txt
read -r x < case.txt
echo "x=$x"
