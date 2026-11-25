# tier: language
# world: seed
declare d=docs/*
local_test() { local l=docs/*; echo "local=[$l]"; }
echo "declare=[$d]"
local_test
