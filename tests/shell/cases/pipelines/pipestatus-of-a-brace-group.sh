# tier: language
# world: none
{ false; }
echo "group: ${PIPESTATUS[*]}"
{ true; } | { false; }
echo "two groups: ${PIPESTATUS[*]}"
