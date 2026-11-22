# tier: language
# world: none
[[ "aaa-bbb-ccc" =~ -.*- ]] && echo "greedy: [${BASH_REMATCH[0]}]"
[[ "abab" =~ (ab)+ ]] && echo "repeat: [${BASH_REMATCH[0]}] last group [${BASH_REMATCH[1]}]"
