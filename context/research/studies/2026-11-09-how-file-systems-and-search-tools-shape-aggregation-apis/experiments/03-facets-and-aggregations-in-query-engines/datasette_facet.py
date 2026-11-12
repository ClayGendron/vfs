"""Run datasette facet queries in-process against corpus.db and print the JSON."""
import asyncio
import json
import sys

from datasette.app import Datasette


async def main(db_path, out_path):
    ds = Datasette([db_path], settings={"default_facet_size": 5, "facet_time_limit_ms": 200})
    await ds.invoke_startup()
    queries = {
        "ext_and_dir_top5": "/corpus/files.json?_facet=ext&_facet=dir&_extra=facet_results,count,suggested_facets&_size=0",
        "ext_filtered_to_py": "/corpus/files.json?ext=py&_facet=dir&_facet_size=3&_extra=facet_results,count&_size=0",
    }
    results = {}
    for name, path in queries.items():
        response = await ds.client.get(path)
        results[name] = {"path": path, "status": response.status_code, "json": response.json()}
    with open(out_path, "w") as fh:
        json.dump(results, fh, indent=2, sort_keys=True)
    print(json.dumps(results, indent=2, sort_keys=True))


asyncio.run(main(sys.argv[1], sys.argv[2]))
