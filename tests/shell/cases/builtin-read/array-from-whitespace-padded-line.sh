# tier: language
# world: none
read -r -a w <<< "   lead   and   trail   "
echo "count=${#w[@]} first=[${w[0]}] last=[${w[-1]}]"
