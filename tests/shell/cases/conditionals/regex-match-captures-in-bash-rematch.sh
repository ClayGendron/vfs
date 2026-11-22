# tier: language
# world: none
s="key=value"
if [[ $s =~ ^([a-z]+)=(.*)$ ]]; then
  echo "whole=[${BASH_REMATCH[0]}]"
  echo "key=[${BASH_REMATCH[1]}] value=[${BASH_REMATCH[2]}]"
  echo "groups=${#BASH_REMATCH[@]}"
fi
