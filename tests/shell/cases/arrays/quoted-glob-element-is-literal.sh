# tier: language
# world: seed
pat=("*.txt")
printf 'quoted: [%s]\n' "${pat[@]}"
printf 'unquoted: [%s]\n' ${pat[@]}
