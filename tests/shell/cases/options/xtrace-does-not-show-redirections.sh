# tier: language
# world: none
{
  set -x
  echo saved >out.txt
  set +x
} 2>&1
read -r line <out.txt
echo "file=$line"
