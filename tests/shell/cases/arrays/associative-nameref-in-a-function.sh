# tier: language
# world: none
setkey() { local -n map=$1; map[$2]=$3; }
declare -A conf
setkey conf host example
setkey conf "the port" 8080
echo "host=${conf[host]} port=${conf[the port]} count=${#conf[@]}"
