import re

from app.agent.price_tool import meal_name
from app.domain.meal_tags import MEAL_DIETS, MEAL_TAGS
from app.domain.plan_revision import PlanRevisionInput

_PROPERTY = (
    r"vegan|vegetarian|dairy(?:[- ]free)?(?: ingredients)?|"
    r"gluten(?:[- ]free)?(?: ingredients)?|high[- ]protein|"
    r"(?:low|lower)[- ]carb|keto|paleo|halal|kosher|"
    r"(?:lactose|nut|egg|soy|sugar)[- ]free|low[- ](?:sodium|fat)|high[- ]fiber"
)
_SUBJECT = (
    r"(?:(?:all|any)(?: of)? |each |which of )?(?:the |my |our )?"
    r"(?:current |saved |selected |planned )?(?:plan |planned )?meals?"
    r"(?: in (?:my |the |our )?(?:current |saved )?plan)?"
    r"|(?:the |my )?[a-z0-9 ]+ in (?:my |the |our )"
    r"(?:current |saved )?plan"
    r"|(?:my |the |our )(?:current |saved )?plan"
    r"|(?:my |the )?(?:planned |selected |saved )[a-z0-9 ]+"
)
_QUESTION = re.compile(
    rf"(?:(?P<which>which) (?:of )?(?P<which_subject>{_SUBJECT}) are |"
    rf"(?:is|are) (?P<subject>{_SUBJECT}) )"
    rf"(?P<not>not )?(?P<property>{_PROPERTY})"
    rf"(?: or (?P<alternative>{_PROPERTY}))?\??",
    re.IGNORECASE,
)
_CONTAINS = re.compile(
    rf"(?:(?P<which>which) (?:of )?(?P<which_subject>{_SUBJECT})|"
    rf"(?:does|do) (?P<subject>{_SUBJECT})) contain "
    r"(?P<property>dairy|gluten)\??",
    re.IGNORECASE,
)
_CLARIFY = "Please ask about one supported characteristic of your saved plan meals."


def current_plan_answer(message: str, plan: PlanRevisionInput | None) -> str | None:
    text = message.strip()
    if text.startswith("My current plan: "):
        prefix, separator, text = text.partition("\n\n")
        if not separator or ". Pantry: " not in prefix or ". Plan cap: " not in prefix:
            return None
    text = " ".join(text.casefold().split())
    match = _QUESTION.fullmatch(text)
    if match is None:
        match = _CONTAINS.fullmatch(text)
    if match is None:
        return None
    groups = match.groupdict()
    subject = groups.get("subject") or groups.get("which_subject") or ""
    if re.search(
        r"\b(?:add|remove|replace|swap|substitute|find|search|cheaper|change)\b",
        subject,
    ):
        return None
    if " in " not in subject and not re.search(
        r"\b(?:plan|planned|saved|selected|current)\b", subject
    ):
        return None
    if groups.get("alternative"):
        return _CLARIFY
    prop = groups["property"].replace("-", " ")
    if prop not in {
        "vegan",
        "vegetarian",
        "dairy",
        "dairy free",
        "dairy ingredients",
        "dairy free ingredients",
        "gluten",
        "gluten free",
        "gluten ingredients",
        "gluten free ingredients",
        "high protein",
        "low carb",
        "lower carb",
    }:
        return _CLARIFY
    if plan is None:
        return "Your saved plan is unavailable. Please open or provide your plan."
    if not plan.snapshot.meals:
        return "Your saved plan has no meals yet."
    meals = plan.snapshot.meals
    if " in " in subject:
        name = subject.split(" in ", 1)[0].removeprefix("the ").removeprefix("my ")
        name = re.sub(
            r"^(?:(?:all|any)(?: of)? |each )?(?:current |saved |selected )?",
            "",
            name,
        )
        if name not in {"meal", "meals", "plan meal", "plan meals"}:
            selected = [
                meal for meal in meals if meal_name(meal.recipe_id).casefold() == name
            ]
            if not selected:
                return "Please name one meal in your saved plan."
            meals = selected
    elif not subject.endswith(("meal", "meals", "plan")):
        name = re.sub(r"^(?:my |the )?(?:planned |selected |saved )", "", subject)
        selected = [
            meal for meal in meals if meal_name(meal.recipe_id).casefold() == name
        ]
        if not selected:
            return "Please name one meal in your saved plan."
        meals = selected
    elif subject.endswith("meal") and len(meals) > 1:
        names = ", ".join(meal_name(meal.recipe_id) for meal in meals)
        return f"Which selected meal do you mean: {names}?"
    if prop in {"vegan", "vegetarian"}:
        key = prop
        label = prop
        diets = True
    elif prop.startswith("dairy") or prop.startswith("gluten"):
        food = "dairy" if prop.startswith("dairy") else "gluten"
        key = f"{food}_free_ingredients"
        label = f"{food} ingredients"
        diets = False
    else:
        key = "high_protein" if prop == "high protein" else "lower_carb"
        label = "high protein" if key == "high_protein" else "lower carb"
        diets = False
    lines: list[str] = []
    for meal in meals:
        matched = key in (MEAL_DIETS if diets else MEAL_TAGS)[meal.recipe_id]
        positive = matched
        if key.endswith("_free_ingredients") and prop in {"dairy", "gluten"}:
            positive = not matched
        if groups.get("which") and positive == bool(groups.get("not")):
            continue
        name = meal_name(meal.recipe_id)
        serving = "serving" if meal.servings == 1 else "servings"
        if key.endswith("_free_ingredients"):
            fact = f"{'has no' if matched else 'has'} {label}"
        else:
            fact = f"is {'not ' if not matched else ''}{label}"
        lines.append(f"{name} ({meal.servings} {serving}) {fact}.")
    if not lines:
        result = "None of the selected meals match that question."
        if key.endswith("_free_ingredients"):
            result += " This checks ingredients only."
        return result
    if key.endswith("_free_ingredients"):
        lines.append("This checks ingredients only.")
    return " ".join(lines)
