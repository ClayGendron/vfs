# tier: language
# world: none
set -- -f '' -v
while getopts f:v opt; do echo "opt=$opt arg=[${OPTARG-unset}]"; done
