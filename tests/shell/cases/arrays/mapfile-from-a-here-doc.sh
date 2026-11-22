# tier: language
# world: none
mapfile lines <<'END'
first line
second line
END
echo "count=${#lines[@]}"
printf '<%s>' "${lines[@]}"; echo
