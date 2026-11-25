# tier: language
# world: seed
( cd docs && echo "inside=$PWD" )
echo "outside=$PWD"
x=$(cd data; pwd)
echo "x=$x PWD=$PWD"
