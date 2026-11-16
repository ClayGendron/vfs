import json, sys, urllib.request
for proj in sys.argv[1:]:
    d = json.load(urllib.request.urlopen(f"https://pypi.org/pypi/{proj}/json"))
    v = d["info"]["version"]; files = d["urls"]
    f = files[0]["filename"]
    req = urllib.request.Request(f"https://pypi.org/integrity/{proj}/{v}/{f}/provenance", headers={"Accept": "application/vnd.pypi.integrity.v1+json"})
    try:
        p = json.load(urllib.request.urlopen(req))
        pub = p["attestation_bundles"][0]["publisher"]
        print(f"{proj} {v}: provenance YES publisher={pub.get('kind')} repo={pub.get('repository')} workflow={pub.get('workflow')}")
    except urllib.error.HTTPError as e:
        print(f"{proj} {v}: provenance NO ({e.code})")
