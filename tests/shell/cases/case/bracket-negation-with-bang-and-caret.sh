# tier: language
# world: none
for c in x 3; do
  case $c in [!0-9]) echo "$c: not a digit (!)" ;; esac
  case $c in [^0-9]) echo "$c: not a digit (^)" ;; esac
done
