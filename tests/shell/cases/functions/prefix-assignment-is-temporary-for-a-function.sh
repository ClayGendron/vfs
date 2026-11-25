# tier: language
# world: none
show() { echo "in show: x=[${x-unset}]"; }
x=global
x=temporary show
echo "after: x=$x"
unset x
x=temporary show
echo "after: x=[${x-unset}]"
