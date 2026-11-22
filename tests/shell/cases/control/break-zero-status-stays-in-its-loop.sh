# tier: language
# world: none
for ((i = 0; i < 1; i++)); do break 0; done
echo "arithmetic for: $?"
for x in a; do break; done
echo "plain break after: $?"
while break 0; do :; done
echo "while condition: $?"
for x in a; do break; done
echo "plain break after that: $?"
