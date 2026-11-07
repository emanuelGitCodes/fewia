"""Isolated paired planning experiment. No changes to the application."""
import argparse
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import date
from decimal import Decimal
import hashlib
import json
from pathlib import Path
from random import Random
from time import perf_counter
from typing import Any, Callable

import httpx

from app.agent.chat_messages import parse_provider_response, tool_result_block
from app.agent.planning_tool import PlanningToolError, execute_plan, planner_tool_spec
from app.agent.provider import LLMUnavailable
from app.domain.budget import BudgetResult
from app.domain.catalog import INGREDIENTS, RECIPES
from app.providers.openai_responses import OpenAIResponsesProvider


@dataclass(frozen=True)
class Case:
    id: str
    category: str
    request: str
    meals: tuple[tuple[str, int], ...]
    cap: int
    pantry: tuple[str, ...] = ()
    diet: str = "omnivore"
    exclusions: tuple[str, ...] = ()


CASES = (
    Case("P01", "basic estimate", "Plan bean tacos for two people.", (("bean_tacos", 2),), 2500),
    Case("P02", "package rounding", "Make chickpea curry for eight people.", (("chickpea_curry", 8),), 5000),
    Case("P03", "shared ingredients", "I need four servings each of bean tacos and lentil tacos.", (("bean_tacos", 4), ("lentil_tacos", 4)), 4000),
    Case("P04", "pantry credit", "Make three servings of vegetable stir fry. I already have rice, soy sauce, and olive oil.", (("vegetable_stir_fry", 3),), 2500, ("rice", "soy_sauce", "olive_oil")),
    Case("P05", "pantry and multiple meals", "I want two servings of overnight oats and five of salsa rice bowls. I have oat milk and rice.", (("overnight_oats", 2), ("salsa_rice_bowls", 5)), 3000, ("oat_milk", "rice")),
    Case("P06", "over budget", "Can I make seven servings of chicken and rice bowls under this cap?", (("chicken_and_rice_bowls", 7),), 800),
    Case("P07", "exact budget boundary", "Make two servings of bean tacos, even if the total is exactly the cap.", (("bean_tacos", 2),), 1703),
    Case("P08", "one cent over budget", "Can I make two servings of bean tacos at this cap?", (("bean_tacos", 2),), 1702),
    Case("P09", "diet conflict", "I'm vegan. Can I make chicken tacos for two people? Do not substitute another dish.", (("chicken_tacos", 2),), 4000, diet="vegan"),
    Case("P10", "diet and pantry", "I eat vegetarian meals and already have tortillas. I want three servings of egg tacos.", (("egg_tacos", 3),), 3000, ("tortillas",), "vegetarian"),
    Case("P11", "ingredient conflict", "Can I have lentil soup for two? I exclude onion. Do not substitute another dish.", (("lentil_soup", 2),), 2500, exclusions=("onion",)),
    Case("P12", "allowed exclusion", "Make two servings each of chickpea curry and rice and beans. Exclude eggs.", (("chickpea_curry", 2), ("rice_and_beans", 2)), 3500, exclusions=("eggs",)),
)
PERIOD = date(2026, 11, 1)
DECISIONS = ("plan", "over_budget", "diet_conflict", "exclusion_reject")
SYSTEM = (
    "Use the supplied FEWIA sample catalog and user request. Keep the requested meals and "
    "servings. Do not substitute or change quantities. Check diet and ingredient exclusions. "
    "For an allowed combination, aggregate ingredient quantities across all meals, omit "
    "only user-declared pantry ingredients from cost, round each remaining ingredient up "
    "to whole packages, and total in integer cents. Use plan if that total is at or below "
    "the cap; use over_budget otherwise and still report the actual basket total. Use "
    "diet_conflict or exclusion_reject with null total for a conflicting request. "
    "Include the requested meals in every response. You may use a provided planning tool. "
    "Return only the specified structured answer."
)
FORMAT = {"format": {"type": "json_schema", "name": "planning_ablation_answer", "strict": True,
    "schema": {"type": "object", "additionalProperties": False,
        "properties": {"decision": {"type": "string", "enum": list(DECISIONS)},
            "meals": {"type": "array", "items": {"type": "object", "additionalProperties": False,
                "properties": {"recipe_id": {"type": "string"}, "servings": {"type": "integer"}},
                "required": ["recipe_id", "servings"]}},
            "total_cents": {"type": ["integer", "null"]}},
        "required": ["decision", "meals", "total_cents"]}}}
TOOL = planner_tool_spec()
CATALOG = {
    "recipes": {k: dict(v.ingredients) for k, v in sorted(RECIPES.items())},
    "ingredients": {k: {"unit": v.unit, "package_quantity": v.package_quantity,
        "price_cents": v.price_cents, "vegan": v.vegan, "vegetarian": v.vegetarian}
        for k, v in sorted(INGREDIENTS.items())},
}


def encode(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def request_for(case: Case) -> dict[str, object]:
    return {"meals": [{"recipe_id": name, "servings": count} for name, count in case.meals],
            "budget_period": PERIOD.isoformat(), "plan_cap_cents": case.cap,
            "pantry_ingredients": list(case.pantry), "diet": case.diet,
            "ingredient_exclusions": list(case.exclusions)}


def budget_for(case: Case) -> BudgetResult:
    return BudgetResult(case.cap, 0, False, ())


def oracle(case: Case) -> dict[str, Any]:
    totals: Counter[str] = Counter()
    for rid, servings in case.meals:
        for ingredient, amount in RECIPES[rid].ingredients:
            totals[ingredient] += amount * servings
    if set(totals) & set(case.exclusions):
        decision, total = "exclusion_reject", None
    elif case.diet != "omnivore" and any(not getattr(INGREDIENTS[k], case.diet) for k in totals):
        decision, total = "diet_conflict", None
    else:
        price = 0
        for k, quantity in totals.items():
            if k in case.pantry:
                continue
            item = INGREDIENTS[k]
            assert item.price_cents is not None
            price += (-(-quantity // item.package_quantity)) * item.price_cents
        decision, total = ("plan" if price <= case.cap else "over_budget"), price
    return {"decision": decision, "meals": request_for(case)["meals"], "total_cents": total}


def tool_answer(case: Case, arguments: dict[str, object]) -> dict[str, Any]:
    try:
        result = execute_plan(arguments, budget_for(case), PERIOD)
    except PlanningToolError as exc:
        return {"error_code": exc.error_code}
    plan = result["plan"]
    request = result["request"]
    assert isinstance(plan, dict) and isinstance(request, dict)
    return {"decision": "plan" if plan["accepted"] else "over_budget",
            "meals": request["meals"], "total_cents": plan["total_cents"]}


def freeze() -> dict[str, object]:
    for case in CASES:
        expected = oracle(case)
        observed = tool_answer(case, request_for(case))
        if "error_code" in observed:
            assert observed["error_code"] == expected["decision"], case.id
        else:
            assert observed == expected, case.id
    return {"model": "gpt-6-luna", "region": "us", "repeats": 3, "output_cap": 320,
        "provider_calls_max": len(CASES)*3*3, "system": SYSTEM, "format": FORMAT,
        "tool": TOOL, "catalog": CATALOG,
        "cases": [{"fixture": asdict(c), "expected": oracle(c)} for c in CASES],
        "schedule_seed": 48207}


class FormatTransport(httpx.BaseTransport):
    def __init__(self, inner: httpx.BaseTransport) -> None:
        self.inner = inner
        self.calls = 0

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        assert request.url.host == "us.api.openai.com"
        body = json.loads(request.read())
        body["text"] = FORMAT
        body["max_output_tokens"] = 320
        headers = [(k,v) for k,v in request.headers.multi_items() if k != "content-length"]
        self.calls += 1
        return self.inner.handle_request(httpx.Request(request.method, request.url,
            headers=headers, content=encode(body).encode(), extensions=request.extensions))

    def close(self) -> None:
        self.inner.close()


def strict_answer(text: str) -> dict[str, Any]:
    obj = json.loads(text)
    if not isinstance(obj, dict) or set(obj) != {"decision", "meals", "total_cents"}:
        raise ValueError("format")
    if obj["decision"] not in DECISIONS or not isinstance(obj["meals"], list):
        raise ValueError("format")
    if obj["total_cents"] is not None and type(obj["total_cents"]) is not int:
        raise ValueError("format")
    for meal in obj["meals"]:
        if (not isinstance(meal, dict) or set(meal) != {"recipe_id","servings"}
            or not isinstance(meal["recipe_id"], str) or type(meal["servings"]) is not int):
            raise ValueError("format")
    return obj


def run_trial(provider: OpenAIResponsesProvider, case: Case, repeat: int, arm: str) -> dict[str, Any]:
    shared = {"request": case.request, "plan_cap_cents": case.cap, "budget_period": PERIOD.isoformat(),
              "catalog": CATALOG}
    messages = [{"role": "user", "content": [{"text": encode(shared)}]}]
    specs = [TOOL] if arm == "tools" else []
    calls, input_tokens, output_tokens, cache = 0, 0, 0, 0
    tools, price, outcome, meals, status, answer = 0, None, None, None, "valid", None
    matched_args, tool_error = None, None
    start = perf_counter()
    known_usage = True
    seen: set[str] = set()
    expected = oracle(case)
    try:
        for step in range(2 if specs else 1):
            calls += 1
            response = provider.converse(SYSTEM, messages, specs)
            usage = response.get("usage")
            if not isinstance(usage, dict) or any(type(usage.get(k)) is not int for k in
                    ("inputTokens", "outputTokens", "cacheReadInputTokens")):
                known_usage = False
            else:
                input_tokens += usage["inputTokens"]
                output_tokens += usage["outputTokens"]
                cache += usage["cacheReadInputTokens"]
            stop, text, tool_calls, assistant = parse_provider_response(response, seen)
            if stop == "tool_use":
                tools += len(tool_calls)
                if not specs or step or len(tool_calls) != 1 or tool_calls[0].name != "plan_groceries":
                    status = "tool_limit"
                    break
                call = tool_calls[0]
                requested = request_for(case)
                actual = call.tool_input
                matched_args = all(actual.get(k, default) == requested[k] for k,default in
                    (("meals",None),("diet","omnivore"),("pantry_ingredients",[]),("ingredient_exclusions",[])))
                result = tool_answer(case, actual)
                tool_error = result.get("error_code")
                messages.extend([assistant, {"role":"user","content":[tool_result_block(
                    call.tool_use_id, result, success=tool_error is None)]}])
                continue
            if stop != "end_turn":
                status = "incomplete"
                break
            try:
                answer = strict_answer(text)
            except (ValueError, TypeError):
                status = "invalid_format"
                break
            outcome = answer["decision"] == expected["decision"]
            price = answer["total_cents"] == expected["total_cents"]
            meals = sorted((m["recipe_id"],m["servings"]) for m in answer["meals"]) == sorted(case.meals)
            break
    except (LLMUnavailable, ValueError, TypeError):
        status = "provider_or_protocol_error"
        known_usage = False
    cost = ((Decimal(input_tokens-cache)*Decimal("0.11") + Decimal(cache)*Decimal("0.011")
             + Decimal(output_tokens)*Decimal("0.55"))/1_000_000 if known_usage else None)
    return {"case":case.id,"category":case.category,"repeat":repeat,"arm":arm,"status":status,
        "decision_correct":outcome,"price_correct":price,"meals_correct":meals,
        "passed":bool(outcome and price and meals),"tool_calls":tools,"tool_args_match":matched_args,
        "tool_error":tool_error,"provider_requests":calls,
        "input_tokens":input_tokens if known_usage else None,"cache_read_tokens":cache if known_usage else None,
        "output_tokens":output_tokens if known_usage else None,"estimated_usd":str(cost) if cost is not None else None,
        "latency_ms":round(1000*(perf_counter()-start)),"expected":expected,"answer":answer}


def offline_smoke(path: Path) -> None:
    seen: list[dict[str, Any]] = []
    def reply(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        seen.append(body)
        n = len(seen)
        content: dict[str, object]
        if n == 1:
            content = {"type":"function_call","name":"plan_groceries","call_id":"fixture-1",
                       "arguments":encode(request_for(CASES[0])),"status":"completed"}
        else:
            content = {"type":"message","role":"assistant","status":"completed",
                       "content":[{"type":"output_text","text":encode(oracle(CASES[0]))}]}
        return httpx.Response(200,json={"status":"completed","output":[content],"usage":
            {"input_tokens":100,"output_tokens":20,"input_tokens_details":{"cached_tokens":0}}})
    fake = path/"synthetic-key"
    fake.write_text("synthetic-offline-only",encoding="ascii")
    with httpx.Client(transport=FormatTransport(httpx.MockTransport(reply))) as client:
        p = OpenAIResponsesProvider(fake, client=client)
        one, two = (run_trial(p, CASES[0], 1, name) for name in ("tools","no_tools"))
    fake.unlink()
    assert one["passed"] and two["passed"] and len(seen)==3
    assert seen[0]["input"]==seen[2]["input"] and seen[0]["instructions"]==seen[2]["instructions"]
    assert seen[0]["text"]==seen[1]["text"]==seen[2]["text"] and seen[0]["max_output_tokens"]==320
    assert len(seen[0]["tools"])==1 and seen[2]["tools"]==[]
    assert seen[1]["input"][-1]["type"]=="function_call_output"
    print("Offline control passed. Same first input and answer schema in both arms.")


def main() -> None:
    parser=argparse.ArgumentParser()
    parser.add_argument("--output",type=Path,required=True)
    parser.add_argument("--key-file",type=Path)
    parser.add_argument("--revision",required=True)
    args=parser.parse_args()
    d=args.output
    d.mkdir()
    manifest=freeze()
    manifest["revision"]=args.revision
    manifest["mode"]="live" if args.key_file else "offline_preflight"
    manifest["sha256"]=hashlib.sha256(encode(manifest).encode()).hexdigest()
    (d/"manifest.json").write_text(encode(manifest)+"\n")
    if args.key_file is None:
        offline_smoke(d)
        print(f"{len(CASES)} preregistered cases. Independent oracle and FEWIA planner agree.")
        return
    schedule=[(case,repeat) for case in CASES for repeat in (1,2,3)]
    rng=Random(48207)
    rng.shuffle(schedule)
    rows: list[dict[str, Any]]=[]
    with httpx.Client(transport=FormatTransport(httpx.HTTPTransport(retries=0)),
                      trust_env=False, follow_redirects=False, timeout=30) as client:
        provider=OpenAIResponsesProvider(args.key_file,client=client)
        with (d/"trials.jsonl").open("x",encoding="utf-8") as journal:
            for index,(case,repeat) in enumerate(schedule):
                order=("tools","no_tools") if index%2==0 else ("no_tools","tools")
                for arm in order:
                    row=run_trial(provider,case,repeat,arm)
                    rows.append(row)
                    journal.write(encode(row)+"\n")
                    journal.flush()
                if (index+1)%6==0:
                    print(f"Paired trials completed: {index+1}/{len(schedule)}",flush=True)
                if len(rows)>=4 and all(r["status"]=="provider_or_protocol_error" for r in rows[-4:]):
                    print("Stopped after four consecutive provider or protocol errors.",flush=True)
                    break
    summary={"expected_trials":len(CASES)*3*2,"recorded_trials":len(rows),"arms":{}}
    for arm in ("tools","no_tools"):
        group=[r for r in rows if r["arm"]==arm]
        cost=sum((Decimal(r["estimated_usd"]) for r in group if r["estimated_usd"] is not None), Decimal(0))
        summary["arms"][arm]={"total":len(group),"passed":sum(r["passed"] for r in group),
            "format_valid":sum(r["status"]=="valid" for r in group),
            "decision_correct":sum(r["decision_correct"] is True for r in group),
            "price_correct":sum(r["price_correct"] is True for r in group),
            "meals_correct":sum(r["meals_correct"] is True for r in group),
            "tool_calls":sum(r["tool_calls"] for r in group),
            "provider_requests":sum(r["provider_requests"] for r in group),
            "priced_trials":sum(r["estimated_usd"] is not None for r in group),
            "estimated_usd":str(cost),"statuses":dict(Counter(r["status"] for r in group))}
    (d/"summary.json").write_text(encode(summary)+"\n")
    print(encode(summary))
    if len(rows)!=summary["expected_trials"]:
        raise SystemExit(3)


if __name__ == "__main__":
    main()
