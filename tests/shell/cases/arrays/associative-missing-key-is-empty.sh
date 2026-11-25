# tier: language
# world: none
declare -A m=([present]=yes)
echo "present=[${m[present]}] missing=[${m[missing]}]"
echo "default=[${m[missing]-none}] set=[${m[present]+set}]"
