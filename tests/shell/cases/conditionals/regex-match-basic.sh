# tier: language
# world: none
[[ abc123 =~ [0-9]+ ]]; echo "digits: $?"
[[ abc =~ [0-9]+ ]]; echo "no digits: $?"
[[ hello =~ ^h.*o$ ]]; echo "anchored: $?"
[[ xhello =~ ^h ]]; echo "anchor fails: $?"
