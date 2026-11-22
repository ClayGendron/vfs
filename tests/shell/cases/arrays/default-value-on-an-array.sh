# tier: language
# world: none
e=()
echo "empty: ${e[@]:-fallback}"
a=(x)
echo "set: ${a[@]:-fallback}"
echo "alt: [${e[@]:+alt}] [${a[@]:+alt}]"
