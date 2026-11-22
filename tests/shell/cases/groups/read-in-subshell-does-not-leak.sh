# tier: language
# world: none
(read -r v <<< "inside"; echo "inside v=$v")
echo "outside v=${v-unset}"
