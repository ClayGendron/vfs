# tier: language
# world: none
declare -r late
late=1 2>/dev/null
echo "status=$? late=[${late-unset}]"
