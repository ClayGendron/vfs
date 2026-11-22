# tier: language
# world: none
n=10
if [ "$n" -eq 10 ]; then echo "eq"; fi
if [ "$n" -ne 3 ]; then echo "ne"; fi
if [ "$n" -gt 9 ] && [ "$n" -le 10 ]; then echo "in range"; fi
if [ -5 -lt 2 ]; then echo "negative compares"; fi
