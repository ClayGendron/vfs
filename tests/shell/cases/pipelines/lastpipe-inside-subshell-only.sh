# tier: language
# world: none
(
  shopt -s lastpipe
  echo inner | read -r v
  echo "in subshell v=[$v]"
)
echo outside | read -r w
echo "parent w=[$w]"
