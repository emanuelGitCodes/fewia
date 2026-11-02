import re

from app.agent.price_tool import meal_name
from app.domain.meal_tags import MEAL_DIETS, MEAL_TAGS
from app.domain.plan_revision import PlanRevisionInput

_QUESTION_PROPERTY = r"[a-z]+(?:[- ][a-z]+)*"
_ROUTED_INTENT = re.compile(
    r"\b(?:budgets?|afford(?:able|ability)?|cost(?:s|ing)?|pric(?:e|es|ing)|"
    r"caps?|limits?|totals?|spend(?:ing)?|spent|money|cheap(?:er|est)?|"
    r"expens(?:e|es|ive)|economical|"
    r"dollars?|cents?|usd|balance|allowance|funds?|sav(?:e|es|ing|ings)|"
    r"safe|allerg(?:y|ies|ic)|celiac|diabet(?:es|ic)|pregnan(?:t|cy)|"
    r"add(?:ing)?|remov(?:e|ing|ed)|replac(?:e|ing|ed)|swap(?:ping|ped)?|"
    r"substitut(?:e|ing|ed)|find|finding|search(?:ing|ed)?|chang(?:e|ing|ed)|"
    r"buy(?:ing)?|bought|purchas(?:e|ing|ed)|order(?:ing|ed)?|"
    r"creat(?:e|ing|ed)|writ(?:e|ing|ten)|show(?:ing)?|give|make|"
    r"shop(?:ping)?|checkout|pay(?:ing)?|deliver(?:ing)?|ship(?:ping)?|"
    r"check(?:ing)?|tell|explain|use|help|updat(?:e|ing)|includ(?:e|ing)|"
    r"exclud(?:e|ing)|choose|prepar(?:e|ing)|send|calculat(?:e|ing)|"
    r"recommend(?:ing|ed)?|suggest(?:ing|ed)?|need|want)\b"
)
_OTHER_CLAUSE = re.compile(
    r"\b(?:but|yet|nor|also|then|if|unless|when|while|because|so|"
    r"please|can|could|would|should|will|are|is|do|does|contains?|your|me)\b"
)
_SUBJECT_PREPOSITION = re.compile(r"\b(?:for|to|with|without)\b")
_CATALOG_NAMES = "|".join(
    re.escape(name)
    for name in sorted(
        (meal_name(recipe_id).casefold() for recipe_id in MEAL_TAGS),
        key=len,
        reverse=True,
    )
)
_CATALOG_NAME = re.compile(rf"\b(?:{_CATALOG_NAMES})\b")
_MEAL_NAME = rf"(?:{_CATALOG_NAMES}|[a-z0-9]+)"
_MEAL_SUBJECT = (
    r"(?:(?:all|any)(?: of)? |each |which of )?(?:the |my |our )?"
    r"(?:current |saved |selected |planned )?(?:plan |planned )?meals?"
    r"(?: in (?:my |the |our )?(?:current |saved )?plan)?"
)
_PLAN_SUBJECT = r"(?:my |the |our )(?:current |saved )?plan"
_SUBJECT = (
    rf"{_MEAL_SUBJECT}"
    r"|(?:the |my )?[a-z0-9 ]+? in (?:my |the |our )"
    r"(?:current |saved )?plan"
    rf"|{_PLAN_SUBJECT}"
    rf"|(?:my |the |our )?(?:planned |selected |saved ){_MEAL_NAME}"
    rf"(?: (?:and|or) {_MEAL_NAME})*"
)
_QUESTION = re.compile(
    rf"(?:(?P<which>which) (?:of )?(?P<which_subject>{_SUBJECT}) are |"
    rf"(?:is|are) (?P<subject>{_SUBJECT}) )"
    rf"(?P<not>not )?(?P<property>{_QUESTION_PROPERTY})\??",
    re.IGNORECASE,
)
_CONTAINMENT_SUBJECT = (
    rf"(?:{_SUBJECT}|(?:my |the |our )?(?:planned |selected |saved )"
    r"[a-z0-9]+(?:[- ][a-z0-9]+)*)"
)
_CONTAINS = re.compile(
    rf"(?:(?P<which>which) (?:of )?(?P<which_subject>{_CONTAINMENT_SUBJECT})|"
    rf"(?:does|do) (?P<subject>{_CONTAINMENT_SUBJECT})) contain "
    rf"(?P<property>{_QUESTION_PROPERTY})\??",
    re.IGNORECASE,
)
_CLARIFY = "Please ask about one supported characteristic of your saved plan meals."
_SUPPORTED_PROPERTIES = {
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
}


def current_plan_answer(message: str, plan: PlanRevisionInput | None) -> str | None:
    text = message.strip()
    if text.startswith("My current plan: "):
        prefix, separator, text = text.partition("\n\n")
        if not separator or ". Pantry: " not in prefix or ". Plan cap: " not in prefix:
            return None
    text = " ".join(text.casefold().split())
    if _ROUTED_INTENT.search(text):
        return None
    match = _QUESTION.fullmatch(text)
    contains = match is None
    if match is None:
        match = _CONTAINS.fullmatch(text)
    if match is None:
        return None
    groups = match.groupdict()
    subject = groups.get("subject") or groups.get("which_subject") or ""
    prop = groups["property"].replace("-", " ")
    compound = re.search(r"\b(?:and|or)\b", prop) is not None
    subject_clauses = _CATALOG_NAME.sub("", subject)
    if (
        _OTHER_CLAUSE.search(subject_clauses)
        or _OTHER_CLAUSE.search(prop)
        or (not contains and _SUBJECT_PREPOSITION.search(subject_clauses))
    ):
        return None
    if compound and re.search(rf"\b(?:and|or) (?:{_SUBJECT})(?: |$)", prop):
        return None
    possessive_meals = re.fullmatch(
        r"(?:(?:all|any)(?: of)? |each )?(?:my|our) meals?", subject
    )
    if (
        " in " not in subject
        and not possessive_meals
        and not re.search(r"\b(?:plan|planned|saved|selected|current)\b", subject)
    ):
        return None
    if compound:
        return _CLARIFY
    if contains and prop not in {"dairy", "gluten"}:
        return _CLARIFY
    if prop not in _SUPPORTED_PROPERTIES:
        return _CLARIFY
    if plan is None:
        return "Your saved plan is unavailable. Please open or provide your plan."
    if not plan.snapshot.meals:
        return "Your saved plan has no meals yet."
    meals = plan.snapshot.meals
    singular_meal = subject.endswith("meal")
    if " in " in subject:
        name = subject.split(" in ", 1)[0]
        name = re.sub(r"^(?:the |my |our )", "", name)
        name = re.sub(
            r"^(?:(?:all|any)(?: of)? |each )?(?:the |my |our )?"
            r"(?:current |saved |selected )?",
            "",
            name,
        )
        if name in {
            "meal",
            "meals",
            "plan meal",
            "plan meals",
            "planned meal",
            "planned meals",
        }:
            singular_meal = name.endswith("meal")
        else:
            singular_meal = False
            selected = [
                meal for meal in meals if meal_name(meal.recipe_id).casefold() == name
            ]
            if not selected:
                return "Please name one meal in your saved plan."
            meals = selected
    elif not re.fullmatch(rf"(?:{_MEAL_SUBJECT}|{_PLAN_SUBJECT})", subject):
        name = re.sub(r"^(?:my |the |our )?(?:planned |selected |saved )", "", subject)
        selected = [
            meal for meal in meals if meal_name(meal.recipe_id).casefold() == name
        ]
        if not selected:
            return "Please name one meal in your saved plan."
        meals = selected
    if singular_meal and len(meals) > 1:
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
