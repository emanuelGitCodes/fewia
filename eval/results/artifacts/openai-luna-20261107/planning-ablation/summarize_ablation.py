"""Check the frozen planning study and write a readable benchmark report."""
import hashlib
import json
import math
from pathlib import Path
from decimal import Decimal
from random import Random
import sys
from typing import Any


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def ms(group: list[dict[str, Any]], p: float) -> int:
    times = sorted(x["latency_ms"] for x in group)
    return times[math.ceil(p * len(times)) - 1]


def main(directory: Path) -> None:
    for line in (directory/"before-live.sha256").read_text().splitlines():
        expected, name = line.split(maxsplit=1)
        assert digest(Path(name)) == expected
    a = json.loads((directory/"preflight/manifest.json").read_text())
    b = json.loads((directory/"live/manifest.json").read_text())
    assert {k:v for k,v in a.items() if k not in ("mode","sha256")} == {
        k:v for k,v in b.items() if k not in ("mode","sha256")}
    d = json.loads((directory/"live/summary.json").read_text())
    rows = [json.loads(l) for l in (directory/"live/trials.jsonl").read_text().splitlines()]
    expected = {x["fixture"]["id"]: x for x in b["cases"]}
    keys = [(r["case"],r["repeat"],r["arm"]) for r in rows]
    assert len(keys) == len(set(keys)) == 72
    assert set(keys) == {(case,repeat,arm) for case in expected for repeat in (1,2,3)
                         for arm in ("tools","no_tools")}
    by = dict(zip(keys, rows, strict=True))
    paired = {"tools_only": 0, "no_tools_only": 0, "both_pass": 0, "both_fail": 0}
    differences = []
    cases = []
    for cid, item in expected.items():
        tool, no = ([by[cid,i,arm] for i in (1,2,3)] for arm in ("tools","no_tools"))
        for left,right in zip(tool,no,strict=True):
            result = (left["passed"],right["passed"])
            paired[{(True,True):"both_pass",(True,False):"tools_only",
                    (False,True):"no_tools_only",(False,False):"both_fail"}[result]] += 1
        l,r = (sum(row["passed"] for row in arm) for arm in (tool,no))
        differences.append((l-r)/3)
        cases.append((cid,item["fixture"]["category"],l,r))
    seed=Random(48207)
    boots=sorted(sum(seed.choices(differences,k=len(differences)))/len(differences) for _ in range(20000))
    lo,hi=(100*boots[int(p*(len(boots)-1))] for p in (.025,.975))
    rows_by_arm={arm:[row for row in rows if row["arm"]==arm] for arm in ("tools","no_tools")}
    status_rows = {}
    for arm,group in rows_by_arm.items():
        value=d["arms"][arm]
        assert len(group)==value["total"]==36
        assert all(row["expected"]==expected[row["case"]]["expected"] for row in group)
        status_rows[arm]=value | {"p50_ms":ms(group,.5),"p95_ms":ms(group,.95)}
    for arm in status_rows.values():
        arm["estimated_usd_per_pass"] = str(
            (Decimal(arm["estimated_usd"]) / arm["passed"]).quantize(Decimal("0.000000001"))
        ) if arm["passed"] and arm["priced_trials"] == arm["total"] else None
    out={"source_revision":b["revision"],"manifest_sha256":digest(directory/"live/manifest.json"),
         "journal_sha256":digest(directory/"live/trials.jsonl"),
         "paired":paired,"arms":status_rows,"scenario_bootstrap_95pp":[round(lo,2),round(hi,2)],
         "by_case":[{"case":c,"category":cat,"tools":l,"no_tools":r} for c,cat,l,r in cases]}
    (directory/"report.json").write_text(json.dumps(out,indent=2)+"\n")
    report=["# FEWIA planning tool ablation", "",
      f"Model GPT-6 Luna through the OpenAI US endpoint. Source revision: `{b['revision']}`.",
      "",
      "Twelve curated cases, three repeats per case, and 36 trials per condition. Both conditions "
      "receive the same requests, sample catalog, instructions, and strict response schema. The "
      "only experimental change is access to FEWIA's deterministic planning tool. The runner "
      "alternates condition order within randomized scenario-repeat pairs.",
      "",
      "Each trial must preserve the requested meals and servings, choose the correct plan or "
      "rejection, and report the exact basket cost where applicable. An independently calculated "
      "reference agreed with FEWIA's planner for all 12 cases before the live run.",
      "",
      "| Measure | Tools available | No tools |","|---|---:|---:|"]
    for key,label in (("passed","Passed all checks"),("format_valid","Valid final format"),
        ("decision_correct","Correct decision"),("meals_correct","Correct meals and servings"),
        ("price_correct","Correct basket cost or expected null"),("tool_calls","Tool calls"),
        ("provider_requests","Provider requests"),("priced_trials","Trials with known price"),
        ("estimated_usd","Estimated model cost in USD"),
        ("estimated_usd_per_pass","Estimated USD per passing trial"),("p50_ms","p50 end-to-end latency in ms"),
        ("p95_ms","p95 end-to-end latency in ms")):
        report.append(f"| {label} | {status_rows['tools'][key]} | {status_rows['no_tools'][key]} |")
    report.extend(["",
      f"Paired repeats: tools alone passed {paired['tools_only']}, no tools alone passed "
      f"{paired['no_tools_only']}, both passed {paired['both_pass']}, and both failed "
      f"{paired['both_fail']}. The descriptive 95% scenario-resampled interval for the tools-minus-"
      f"no-tools pass difference is {lo:+.1f} to {hi:+.1f} percentage points. Resampling uses "
      "20,000 draws over the 12 fixed scenarios and keeps repeats together.",
      "",
      "| Case | Capability | Tools passes | No-tools passes |","|---|---|---:|---:|"])
    for cid,cat,l,r in cases:
        report.append(f"| {cid} | {cat} | {l}/3 | {r}/3 |")
    report.extend(["","## Representative errors",""])
    for arm,group in rows_by_arm.items():
        failures=[x for x in group if not x["passed"]]
        if not failures:
            report.append(f"- {arm}: no failed trial in these cases.")
            continue
        examples: dict[str,dict[str,Any]]={}
        for x in failures:
            examples.setdefault(x["case"],x)
        for x in sorted(examples.values(),key=lambda y:y["case"])[:4]:
            g=x["expected"]
            v=x["answer"] or {}
            failed=", ".join(k.removesuffix("_correct") for k in
                ("decision_correct","price_correct","meals_correct") if x[k] is False)
            expected_cost="null" if g["total_cents"] is None else f"{g['total_cents']} cents"
            actual_cost="null" if v.get("total_cents") is None else f"{v['total_cents']} cents"
            detail=""
            if x["meals_correct"] is False:
                detail=f" Expected meals: {g['meals']}. Returned meals: {v.get('meals')}."
            report.append(f"- {arm}, {x['case']} repeat {x['repeat']} ({failed or x['status']}): "
                          f"expected {g['decision']} and {expected_cost}. Got "
                          f"{v.get('decision',x['status'])} and {actual_cost}.{detail}")
    threshold = [by["P08",i,arm] for arm in ("tools","no_tools") for i in (1,2,3)]
    if all(r["passed"] for r in threshold[:3]) and all(r["decision_correct"] is False for r in threshold[3:]):
        report.extend(["", "The one-cent budget boundary shows why a wrong total matters. The actual "
            "basket cost was $17.03 and the cap was $17.02. The tool condition rejected the plan "
            "in all three repeats. The no-tools condition returned a plan in all three."])
    report.extend(["",
       "This ablation covers the planning core and fixed requested meals. It does not measure "
       "arbitrary meal discovery, browser performance, retailer behavior, or model intelligence "
       "outside these cases. The separate Nova–Luna comparison measures the full conversation "
       "suite with tools enabled in both arms. Do not combine their denominators.",
       "",
       "[Frozen experiment](live/manifest.json) · [Sanitized trials](live/trials.jsonl) · "
       "[Structured results](report.json) · [Reproducer](run_ablation.py)"])
    (directory/"report.md").write_text("\n".join(report)+"\n")
    print(json.dumps(out,indent=2))


if __name__=="__main__":
    main(Path(sys.argv[1]))
