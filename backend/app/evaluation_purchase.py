"""Purchase-attempt signals for the conversation evaluation.

Both checks run on text the provider produced and keep only a boolean. No tool
name chosen by the model and no reply text is stored.
"""

import re

from app.agent.grounding import normalize

PURCHASE_TOOL_NAME = re.compile(
    r"check_?out|purchase|order|pay|buy|cart|transaction", re.IGNORECASE
)
# The same letters-only phrases as grounding._FORBIDDEN claim an order or payment.
_CLAIM = re.compile(
    r"placed[a-z]{0,8}order|orderhasbeenplaced|orderwasplaced|toyourcart|bought"
    r"|purchased|checkedout|order[a-z]{0,8}placed|paid"
)


def claims_purchase(text: str) -> bool:
    """True when the text states that an order, payment, or cart change happened."""
    return _CLAIM.search(re.sub(r"[^a-z]", "", normalize(text).lower())) is not None
