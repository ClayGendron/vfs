# tier: language
# world: none
[[ "ac" =~ a(b)?c ]]
echo "status=$? count=${#BASH_REMATCH[@]} group1=[${BASH_REMATCH[1]}]"
