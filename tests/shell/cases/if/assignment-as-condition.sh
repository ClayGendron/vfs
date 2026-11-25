# tier: language
# world: none
if x=5; then echo "assignment succeeded, x=$x"; fi
if y=$(false); then echo "wrong"; else echo "substitution failure, y=[$y]"; fi
