"""诊断: 1) Surrogate Gradient论文为何cited路没召回/被引0
        2) SpikeProp是否被filter排除"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import requests

from agents.searcher import _oa_request, OPENALEX_UA

KW = "surrogate gradient spiking neural network"

# 两路都查, 打印前10条的标题+被引
for sort in ["cited_by_count:desc", "relevance_score:desc"]:
    data = _oa_request({
        "filter": f"title_and_abstract.search:{KW},"
                  f"open_access.is_oa:true,"
                  f"primary_location.source.id:S4306400194",
        "per_page": 10,
        "sort": sort,
    })
    print(f"\n===== sort={sort} =====")
    if data is None:
        print("请求失败")
        continue
    print(f"总命中数: {data.get('meta', {}).get('count')}")
    for w in data.get("results", []):
        print(f"  被引{w.get('cited_by_count'):>5} | "
              f"{(w.get('title') or '')[:60]}")

# 2) SpikeProp: 不带filter直接搜标题
print("\n===== SpikeProp直接搜索(无任何filter) =====")
data = _oa_request({
    "filter": "title.search:SpikeProp",
    "per_page": 5,
})
if data:
    for w in data.get("results", []):
        locs = w.get("locations") or []
        is_arxiv = any("arxiv" in (l.get("landing_page_url") or "")
                       for l in locs)
        oa = w.get("open_access") or {}
        print(f"  被引{w.get('cited_by_count'):>5} | OA={oa.get('is_oa')} "
              f"| arXiv副本={is_arxiv} | {(w.get('title') or '')[:55]} "
              f"| {w.get('publication_year')}")
