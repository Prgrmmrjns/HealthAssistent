"""Central configuration knobs that are not secrets.

Edit these values to change behavior without touching code:
- RUN_MEAL_ANALYSIS: whether to use the Meals DB + Mistral analysis
- model: Mistral model name for image analysis
"""

RUN_MEAL_ANALYSIS: bool = True
MEAL_INSTRUCTIONS = "I am a vegan living in Germany. If you see any products resembling meat or dairy products, please assume that they are plant-based alternatives."

# Mistral model to use for analyzing meal images.
model: str = "mistral-small-2603"

SYNC_PRIOR_GARMIN_DAYS: int = 30

