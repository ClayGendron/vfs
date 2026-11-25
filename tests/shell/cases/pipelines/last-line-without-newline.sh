# tier: language
# world: none
printf 'a\nb' | while IFS= read -r l || [ -n "$l" ]; do echo "[$l]"; done
