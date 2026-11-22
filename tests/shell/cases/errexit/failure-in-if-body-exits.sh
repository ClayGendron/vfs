# tier: language
# world: none
set -e
if true; then
  echo "in body"
  false
  echo "not reached"
fi
echo "not reached either"
