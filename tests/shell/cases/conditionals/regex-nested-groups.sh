# tier: language
# world: none
[[ "2026-11-21" =~ ^(([0-9]{4})-([0-9]{2}))-([0-9]{2})$ ]]
for i in "${!BASH_REMATCH[@]}"; do echo "$i=[${BASH_REMATCH[i]}]"; done
