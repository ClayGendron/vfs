# tier: language
# world: none
line='value  # comment # more'
echo "[${line%%#*}] [${line%#*}]"
