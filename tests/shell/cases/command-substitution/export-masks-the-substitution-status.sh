# tier: language
# world: none
export x=$(exit 3)
echo "export: $?"
declare y=$(exit 4)
echo "declare: $?"
